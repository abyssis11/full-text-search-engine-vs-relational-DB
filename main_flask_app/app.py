from flask import Flask, request, jsonify, make_response, render_template
from flask_sqlalchemy import SQLAlchemy
from os import environ
from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk
import tqdm
import subprocess
import requests
import csv

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = environ.get('DB_URL')
db = SQLAlchemy(app)

MAX_SIZE = 10000

class Car(db.Model):
    __tablename__ = 'cars'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    engine = db.Column(db.Text)
    #year = db.Column(db.Integer)
    #price = db.Column(db.Integer)

    def json(self):
        return {'id': self.id,'name': self.name, 'engine': self.engine}


def load_csv_into_db():
    num = 300000
    br = 0
    with open('UBER_REVIEWS.csv', 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            br += 1
            if br == num:
                break
            author_name = row.get('author_name')
            review_text = row.get('review_text')

            record = Car(name = name, engine = engine)
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

def load_csv_into_es():
    num = 300000
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

# Function to delete all data from the table
def delete_all_data():
    try:
        # Use the `delete()` method to delete all rows
        db.session.query(Car).delete()
        db.session.commit()
        print("All data deleted successfully.")
    except Exception as e:
        print(f"Error deleting data: {str(e)}")
        db.session.rollback()
    finally:
        db.session.close()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/hello")
def hello():
    return "hello"

@app.route("/load")
def load():
    load_csv_into_db()
    return "loaded"

@app.route("/loades")
def loades():
    es = Elasticsearch(["http://elasticsearch:9200/"])
    create_index(es)
    progress = tqdm.tqdm(unit="docs", total=300000)
    successes = 0
    for ok, action in streaming_bulk(
        client=es, index="reviews", actions=load_csv_into_es(),
    ):
        progress.update(1)
        successes += ok
    #num = 100
    #br = 0
    '''with open("UBER_REVIEWS.csv", "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            br += 1
            if br == num:
                break
            document = {
                "author_name": row.get('author_name'),
                "review_text": row.get('review_text')
            }
            es.index(index="reviews", document=document)'''
    return "loaded"


@app.route('/cars', methods=['GET'])
def get_cars():
  try:
    cars = Car.query.all()
    return make_response(jsonify([car.json() for car in cars]), 200)
  except e:
    return make_response(jsonify({'message': 'error getting cars'}), 500)

@app.route('/delete', methods=['GET'])
def delete():
    delete_all_data()
    return 'deleted'

@app.route('/find', methods=['GET'])
def find():
    rez = []
    dic = {}
    word = request.args.get('q')
    look_for = '%{0}%'.format(word)
    rows_with_ho = Car.query.filter(Car.engine.ilike(look_for)).all()
    #query = select(Car).where(Car.column.contains("late"))
    #results = await db.execute(query)
    #data = results.scalars().all()
    for row in rows_with_ho:
            rez.append({"ID": row.id, "Name": row.name, "Engine": row.engine})
    db.session.close()

    return  jsonify(results = rez)

@app.route('/es-search', methods=['GET'])
def es_search():
    query = request.args.get('q').lower()
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
    return jsonify(results = rez)

@app.route('/test-endpoint', methods=['POST'])
def test_endpoint():
    # Get the URL to test from query parameters
    url_to_test = request.form.get('url')
    total_requests = request.form.get('total_requests', default=1000, type=int)  # Default to 1000 if not specified
    concurrency = request.form.get('concurrency', default=10, type=int)         # Default to 10 if not specified
    if not url_to_test:
        return jsonify({"error": f"No URL provided: {url_to_test}"}), 400

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

