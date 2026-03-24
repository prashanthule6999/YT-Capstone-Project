from flask import Flask, render_template, request
import mlflow
import pickle
import os
from threading import Lock
from prometheus_client import Counter, Histogram, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
import time
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
import string
import logging
import re
import dagshub
import nltk
import os
import nltk
from nltk.corpus import stopwords

def ensure_nltk_data():
    nltk_data_path = os.getenv("NLTK_DATA", os.path.expanduser("~/nltk_data"))
    nltk.data.path.append(nltk_data_path)

    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', download_dir=nltk_data_path)

    try:
        nltk.data.find('corpora/wordnet')
    except LookupError:
        nltk.download('wordnet', download_dir=nltk_data_path)

# ✅ Ensure NLTK data is available before using stopwords
ensure_nltk_data()

# Now it's safe to initialize STOP_WORDS
STOP_WORDS = set(stopwords.words("english"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def lemmatization(text):
    """Lemmatize the text."""
    lemmatizer = WordNetLemmatizer()
    text = text.split()
    text = [lemmatizer.lemmatize(word) for word in text]
    return " ".join(text)

# def remove_stop_words(text):
#     """Remove stop words from the text."""
#     stop_words = set(stopwords.words("english"))
#     text = [word for word in str(text).split() if word not in stop_words]
#     return " ".join(text)

def remove_stop_words(text):
    text = [word for word in str(text).split() if word not in STOP_WORDS]
    return " ".join(text)

def removing_numbers(text):
    """Remove numbers from the text."""
    text = ''.join([char for char in text if not char.isdigit()])
    return text

def lower_case(text):
    """Convert text to lower case."""
    text = text.split()
    text = [word.lower() for word in text]
    return " ".join(text)

def removing_punctuations(text):
    """Remove punctuations from the text."""
    text = re.sub('[%s]' % re.escape(string.punctuation), ' ', text)
    text = text.replace('؛', "")
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def removing_urls(text):
    """Remove URLs from the text."""
    url_pattern = re.compile(r'https?://\S+|www\.\S+')
    return url_pattern.sub(r'', text)

# def remove_small_sentences(df):
#     """Remove sentences with less than 3 words."""
#     for i in range(len(df)):
#         if len(df.text.iloc[i].split()) < 3:
#             df.text.iloc[i] = np.nan

def normalize_text(text):
    text = lower_case(text)
    text = remove_stop_words(text)
    text = removing_numbers(text)
    text = removing_punctuations(text)
    text = removing_urls(text)
    text = lemmatization(text)

    return text

# Below code block is for local use
# -------------------------------------------------------------------------------------
# mlflow.set_tracking_uri('https://dagshub.com/prashanthule6999/YT-Capstone-Project.mlflow')
# dagshub.init(repo_owner='prashanthule6999', repo_name='YT-Capstone-Project', mlflow=True)
# -------------------------------------------------------------------------------------

# Below code block is for production use
# -------------------------------------------------------------------------------------
# Set up DagsHub credentials for MLflow tracking
dagshub_token = os.getenv("CAPSTONE_TEST")
if not dagshub_token:
    raise EnvironmentError("CAPSTONE_TEST environment variable is not set")

os.environ["MLFLOW_TRACKING_USERNAME"] = dagshub_token
os.environ["MLFLOW_TRACKING_PASSWORD"] = dagshub_token

dagshub_url = "https://dagshub.com"
repo_owner = "prashanthule6999"
repo_name = "YT-Capstone-Project"
# Set up MLflow tracking URI
mlflow.set_tracking_uri(f'{dagshub_url}/{repo_owner}/{repo_name}.mlflow')
# -------------------------------------------------------------------------------------


# Initialize Flask app
app = Flask(__name__)

# from prometheus_client import CollectorRegistry

# Create a custom registry
registry = CollectorRegistry()

# Define your custom metrics using this registry
REQUEST_COUNT = Counter(
    "app_request_count", "Total number of requests to the app", ["method", "endpoint"], registry=registry
)
REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds", "Latency of requests in seconds", ["endpoint"], registry=registry
)
PREDICTION_COUNT = Counter(
    "model_prediction_count", "Count of predictions for each class", ["prediction"], registry=registry
)

# ------------------------------------------------------------------------------------------
# Model and vectorizer setup
model_name = "my_model"
def get_latest_model_version(model_name):
    client = mlflow.MlflowClient()
    latest_version = client.get_latest_versions(model_name, stages=["Production"])
    if not latest_version:
        latest_version = client.get_latest_versions(model_name, stages=["None"])
    return latest_version[0].version if latest_version else None

# model_version = get_latest_model_version(model_name)
model_version = get_latest_model_version(model_name)
if model_version is None:
    raise ValueError(f"No versions found for model: {model_name}")

model_uri = f'models:/{model_name}/{model_version}'
# print(f"Fetching model from: {model_uri}")
logging.info(f"Fetching model from: {model_uri}")
# model = mlflow.pyfunc.load_model(model_uri)
model = None
model_lock = Lock()

def load_model():
    global model
    if model is None:
        with model_lock:
            if model is None:  # double check
                model = mlflow.pyfunc.load_model(model_uri)
    return model


# vectorizer = pickle.load(open('models/vectorizer.pkl', 'rb'))
with open('models/vectorizer.pkl', 'rb') as f:
    vectorizer = pickle.load(f)

# Routes
@app.route("/")
def home():
    REQUEST_COUNT.labels(method="GET", endpoint="/").inc()
    start_time = time.time()
    response = render_template("index.html", result=None)
    REQUEST_LATENCY.labels(endpoint="/").observe(time.time() - start_time)
    return response

@app.before_first_request
def initialize():
    ensure_nltk_data()
    load_model()

@app.route("/predict", methods=["POST"])
def predict():
    REQUEST_COUNT.labels(method="POST", endpoint="/predict").inc()
    start_time = time.time()

    # text = request.form["text"]
    text = request.form.get("text", "")

    if not text.strip():
        return render_template("index.html", result="Please enter valid text")
    # Clean text
    text = normalize_text(text)
    # Convert to features
    features = vectorizer.transform([text])
    # features_df = pd.DataFrame(features.toarray(), columns=[str(i) for i in range(features.shape[1])])

    # Predict
    # result = model.predict(features_df.values)
    # result = model.predict(features.toarray())
    model_instance = load_model()
    result = model_instance.predict(features.toarray())
    # prediction = result[0]
    label_map = {0: "Negative", 1: "Positive"}
    prediction = label_map.get(result[0], str(result[0]))

    # Increment prediction count metric
    PREDICTION_COUNT.labels(prediction=str(prediction)).inc()

    # Measure latency
    REQUEST_LATENCY.labels(endpoint="/predict").observe(time.time() - start_time)

    return render_template("index.html", result=prediction)

@app.route("/metrics", methods=["GET"])
def metrics():
    """Expose only custom Prometheus metrics."""
    return generate_latest(registry), 200, {"Content-Type": CONTENT_TYPE_LATEST}

@app.route("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    # app.run(debug=True) # for local use
    app.run(debug=True, host="0.0.0.0", port=5000)  # Accessible from outside Docker
