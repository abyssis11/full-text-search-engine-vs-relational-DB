from flask import Flask, request, jsonify, make_response, render_template
from flask_sqlalchemy import SQLAlchemy
from os import environ
from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk
import tqdm
import requests
import csv

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = environ.get('DB_URL')
db = SQLAlchemy(app)

MAX_SIZE = 10000

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_name = db.Column(db.String(255))
    review_text = db.Column(db.Text)

    def json(self):
        return {'id': self.id,'author_name': self.author_name, 'review_text': self.review_text}


def load_csv_into_db(n):
    num = n
    br = 0
    with open('UBER_REVIEWS.csv', 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            br += 1
            if br == num:
                break
            author_name = row.get('author_name')
            review_text = row.get('review_text')

            record = Review(author_name = author_name, review_text = review_text)
            db.session.add(record)
        db.session.commit()

def create_index(client):
    """Creates an index in Elasticsearch if one isn't already there."""
    client.indices.create(
        index="reviews",
        body={
            "settings": {"number_of_shards": 1},
            "mappings": {
                "properties": {
                    "author_name": {"type": "text"},
                    "review_text": {"type": "text"}
                }
            },
        },
        ignore=400,
    )

def load_csv_into_es(n):
    num = n
    br = 0
    with open("UBER_REVIEWS.csv", "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            br += 1
            if br == num:
                break
            document = {
                "author_name": row.get('author_name'),
                "review_text": row.get('review_text')
            }
            yield document

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/load", methods=['POST'])
def load():
    n_reviews = int(request.form.get('reviews'))
    es = Elasticsearch(["http://elasticsearch:9200/"])
    create_index(es)
    query = {"query": {"match_all": {}}}
    es.delete_by_query(index="reviews", body=query, conflicts='proceed')
    progress = tqdm.tqdm(unit="docs", total=n_reviews)
    successes = 0
    for ok, action in streaming_bulk(
        client=es, index="reviews", actions=load_csv_into_es(n_reviews),
    ):
        progress.update(1)
        successes += ok
    load_csv_into_db(n_reviews)
    return "loaded"


@app.route('/pg-search', methods=['GET'])
def find():
    rez = []
    dic = {}
    word = (request.args.get('q') or request.args.get('search-pg')).lower()
    look_for = '%{0}%'.format(word)
    rows_with_ho = Review.query.filter(Review.review_text.ilike(look_for)).limit(MAX_SIZE).all()
    for row in rows_with_ho:
            rez.append(row.review_text)
    db.session.close()

    rez.insert(0, len(rez))
    return  jsonify(results = rez)

@app.route('/es-search', methods=['GET'])
def es_search():
    query = (request.args.get('q') or request.args.get('search-es')).lower()
    tokens = query.split(" ")
    es = Elasticsearch(["http://elasticsearch:9200/"])
    clauses = [
        {
            "span_multi": {
                "match": {"fuzzy": {"review_text": {"value": i, "fuzziness": "AUTO"}}}
            }
        }
        for i in tokens
    ]

    payload = {
        "bool": {
            "must": [{"span_near": {"clauses": clauses, "slop": 0, "in_order": False}}]
        }
    }

    resp = es.search(index="reviews", query=payload, size=MAX_SIZE)
    rez = [result['_source']['review_text'] for result in resp['hits']['hits']]
    rez.insert(0, len(rez))
    return jsonify(results = rez)

@app.route('/test-endpoint', methods=['POST'])
def test_endpoint():
    search = request.form.get('search-es') or request.form.get('search-pg')
    url_to_test = request.form.get('url')
    total_requests = request.form.get('total_requests', default=1000, type=int)  # Default to 1000 if not specified
    concurrency = request.form.get('concurrency', default=10, type=int)         # Default to 10 if not specified
    if not url_to_test:
        return jsonify({"error": f"No URL provided: {url_to_test}"}), 400

    url_to_test = url_to_test + search.replace(' ','%20')

    data = {
        "url": url_to_test,
        "total_requests": total_requests,
        "concurrency": concurrency
    }

    ab_container_url = 'http://apache-ab:4001/run-ab'
    
    try:
        response = requests.post(ab_container_url, json=data)
        return jsonify({"message": "ApacheBench test completed", "output": response.text})
    except requests.RequestException as e:
        return jsonify({"error": "Error communicating with ApacheBench container", "details": str(e)}), 500


if __name__ == '__main__':
    with app.app_context():
        db.drop_all()
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=4000)

