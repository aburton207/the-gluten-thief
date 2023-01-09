from flask import Flask, render_template, request
import concurrent.futures
import requests
import os

from product_data_parser import ProductDataParser
from supermarket import SupermarketAPI

# Create the Flask application
app = Flask(__name__)
DEBUG = False
GEOCODER_API_KEY = os.getenv("GEOCODER_API_KEY")

# Define the route for the index page
@app.route("/")
def index():
    # Render the index.html template in the /templates directory
    return render_template("index.html")


@app.route("/search", methods=("GET", "POST"))
def search():
    print(request)
    if "query" and "postal_code" in request.form:
        query = request.form["query"]
        postal_code = request.form["postal_code"]

        # Look up users postal code, convert to lat & long to search for user's local stores
        # Get each store's normalized data using ProductDataParser
        products_data = SupermarketAPI(query)
        parser = ProductDataParser

        if postal_code is None:
            raise Exception("Postal code is required")

        if DEBUG is True:
            longitude = "-115.02"
            latitude = "49.509724"
        else:
            longitude, latitude = lookup_postal_code(postal_code)

        if latitude is None:
            raise Exception("No geo coords!")

        d = products_data.search_stores_pc(
            latitude, longitude, store_brand="superstore"
        )
        pc_store_id = d["ResultList"][0]["Attributes"][0]["AttributeValue"]

        e = products_data.search_stores_saveon(latitude, longitude)
        saveon_store_id = e["items"][0]["retailerStoreId"]

        walmart_store = products_data.search_stores_walmart(postal_code)

        # Set default stores (closest store)
        products_data.set_store_pc(pc_store_id)
        products_data.set_store_saveon(saveon_store_id)
        products_data.set_store_walmart(latitude, longitude, postal_code)

        # Set up a list of functions to send requests to
        functions = [products_data.query_saveon, products_data.query_pc, products_data.query_safeway, products_data.query_walmart]

        # Use a ThreadPoolExecutor to send the requests in parallel
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Start the load operations and mark each future with its function
            future_to_function = {executor.submit(func): func for func in functions}
            results = {}
            for future in concurrent.futures.as_completed(future_to_function):
                func = future_to_function[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f'Function {func.__name__} generated an exception: {exc}')
                    results[func.__name__] = exc
                else:
                    print(f'Function {func.__name__} returned result: {result}')
                    results[func.__name__] = result


        a = results['query_pc']
        c = results['query_saveon']
        b = results['query_safeway']
        f = results['query_walmart']


        # Check if we have results for all stores
        # TODO: rewrite this
        if all([a, b, c, f]):

            search_data = {
                "store_name": {
                    "pc": d["ResultList"][0]["Name"],
                    "saveon": e["items"][0]["name"],
                    "safeway": "safewaySTORENAME",
                    "walmart": str(walmart_store["payload"]["stores"][0]["id"])
                    + " - "
                    + walmart_store["payload"]["stores"][0]["displayName"],
                },
                "results": {
                    "safeway": parser.parse_safeway_json_data(b),
                    "saveon": parser.parse_saveonfoods_json_data(c),
                    "pc": parser.parse_pc_json_data(a),
                    "walmart": parser.parse_walmart_json_data(f),
                },
            }
        else:
            search_data = {"error": "No results"}

        return render_template("search.html", result_data=search_data)


# Look up postal code to lat,long coords
def lookup_postal_code(postal_code):
    url = (
        "https://geocoder.ca/?postal={postal_code}&auth="
        + GEOCODER_API_KEY
        + "&geoit=XML".format(postal_code=postal_code)
    )
    response = requests.get(url)
    if response.status_code == 200:
        data = response.text
        longitude = data.split("<longt>")[1].split("</longt>")[0]
        latitude = data.split("<latt>")[1].split("</latt>")[0]
        return longitude, latitude


# Run the app
if __name__ == "__main__":
    app.run()
