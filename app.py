from flask import Flask, render_template, request, redirect, flash, session, json
from passlib.hash import pbkdf2_sha256
from flask_moment import Moment
import pymongo
from bson.objectid import ObjectId
from datetime import datetime
from dotenv import load_dotenv
import os
from datetime import date

app_path = os.path.join(os.path.dirname(__file__), '.')
dotenv_path = os.path.join(app_path, '.env')
load_dotenv(dotenv_path)
app = Flask(__name__)
moment = Moment(app)
app.secret_key = os.environ.get("SECRETKEY")

connectionString = os.environ.get("MONGOSTRING")

cluster = pymongo.MongoClient(connectionString)

database = cluster["myFoodationDatabase"]   

drivers_collection = database["donationDrivers"]
shops_collection = database["shops"]
recipients_collection = database["recipients"]

food_collection = database["food"]

def assign_status_class(food):
    status = food.get("status", "")

    if status == "waiting for delivery driver":
        food["status_class"] = "bg-secondary text-light"
    elif status == "driver coming":
        food["status_class"] = "bg-warning text-dark"
    elif status == "driver picked up food":
        food["status_class"] = "bg-info text-dark"
    elif status == "delivered":
        food["status_class"] = "bg-success text-light"
    elif status == "expired":
        food["status_class"] = "bg-danger text-light"
    else:
        food["status_class"] = "bg-secondary text-light"


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")
    role = request.form.get("role")

    collection = None
    if role == "donation_driver":
        collection = drivers_collection
    elif role == "shop_owner":
        collection = shops_collection
    elif role == "donation_recipient":
        collection = recipients_collection
    else:
        flash("Invalid role selected.")
        return redirect("/")

    user = collection.find_one({"email": email})

    if user != None:
        if pbkdf2_sha256.verify(password, user["password"]):
            session["user"] = {"full_name": user.get("full_name"), "email": user.get("email"), "role": role}
            if session["user"]["role"] == "shop_owner":
                session["user"] = {"full_name": user.get("full_name"), "email": user.get("email"), "role": role, "shop_name" : shops_collection.find_one({"email" : user.get("email")}).get("shop name")}
            flash("Sign in succesful", "success")
            return redirect("/home")
        else:
            flash("Invalid password.", "warning")
            return redirect("/")    
        
    else:
        flash("Invalid email", "warning")
        return redirect("/")

@app.route("/signup", methods=["POST"])
def signup():
    
    full_name = request.form.get("full_name")
    email = request.form.get("email")
    password = request.form.get("password")

    encpassword = pbkdf2_sha256.hash(password)

    age = request.form.get("age")
    address = request.form.get("address")
    role = request.form.get("role")
    if role=="donation_driver":
        record={"full_name":full_name, "email":email, "password":encpassword, "age":age, "address":address}
        drivers_collection.insert_one(record)
        session["user"] = {"full_name": full_name, "email": email, "role": role}
    if role=="shop_owner":
        record={"full_name":full_name, "email":email, "password":encpassword, "age":age, "address":address, "shop_name" : request.form.get("shop_name")}
        shops_collection.insert_one(record)
        session["user"] = {"full_name": full_name, "email": email, "role": role, "shop_name" : request.form.get("shop_name")}
    if role=="donation_recipient":
        record={"full_name":full_name, "email":email, "password":encpassword, "age":age, "address":address, "activerequests" : [], "pastrequests" : []}
        recipients_collection.insert_one(record)
        session["user"] = {"full_name": full_name, "email": email, "role": role}
        
    

    return redirect("/home")

@app.route("/home")
def home():
    if "user" not in session:
        flash("Please log in to continue", "danger")
        return redirect("/")
    if session["user"]["role"] == "shop_owner":

        totalnumberoffoodsDonated = food_collection.count_documents({"name of donor" : session["user"]["full_name"], "status":"delivered"})

        return render_template("signed in.html", user=session["user"], totalDonatedFood = totalnumberoffoodsDonated)  

    return render_template("signed in.html", user=session["user"])        

@app.route("/logout")
def logout():
    session.clear()

    flash("Succesfully logged out", "success")
    return redirect("/")

@app.route("/donate", methods=["GET", "POST"])
def donate():
    if request.method == "GET":

        foodsDonated = food_collection.find({"name of donor" : session["user"]["full_name"]})

        return render_template("donate.html", foodsDonated = foodsDonated)
    if request.method == "POST":
        
        quantity = int(request.form.get("quantity"))
        foodname = request.form.get("food_name")
        expir = request.form.get("expiration_date")
        donorname = request.form.get("donor_name")
        shopname = request.form.get("shop_name")
        dateDonated = date.today()
        date_string = dateDonated.strftime("%Y-%m-%d")

        exp_date = datetime.strptime(expir, "%Y-%m-%d").date()
        if exp_date < date.today():
            flash("❌ Cannot submit expired food!", "danger")
            return redirect("/donate")

        record = {"quantity": quantity, "food name":foodname, "expiration date" : expir, "name of donor" : donorname, "date donated" : date_string, "shop name" : shopname, "status" : "waiting for delivery driver", "requeststatus" : "Unrequested"}
        food_collection.insert_one(record)
        flash("donation submitted thank you", "success")
        return redirect("/donate")

@app.route("/drive", methods=["GET", "POST"])
def drive():
    if request.method == "GET":

        foodsDonated = list(food_collection.find({
    "status": "waiting for delivery driver",
    "requeststatus": "requested"
}))

        today = date.today()    

        expiringFoods = []

        i = 0

        while i < len(foodsDonated):
            food = foodsDonated[i]
            exp_date = datetime.strptime(food["expiration date"], "%Y-%m-%d").date()
            food["days_until_expiration"] = (exp_date - today).days
            i+=1
            if food["days_until_expiration"] < 0:
                i-=1
                foodsDonated.pop(i)
                

        for food in foodsDonated:
            # Convert expiration date string to date object
            exp_date = datetime.strptime(food["expiration date"], "%Y-%m-%d").date()
            food["days_until_expiration"] = (exp_date - today).days

            # Add to expiringFoods if expires in 5 days or less
            if food["days_until_expiration"] <= 5 and food["days_until_expiration"] >= 0:
                expiringFoods.append(food)

        return render_template("driver.html", foodsDonated = foodsDonated, today = today, expiringFoods = expiringFoods)
    
@app.route("/recieve", methods=["GET", "POST"])
def recieve():
    if request.method == "GET":
        foodsDonated = list(food_collection.find({
            "quantity": {"$gt": 0},
            "requeststatus": "Unrequested",
            "status": "waiting for delivery driver"
        }))

        today = date.today()

        for food in foodsDonated:
            exp_date = datetime.strptime(food["expiration date"], "%Y-%m-%d").date()
            food["days_until_expiration"] = (exp_date - today).days
            assign_status_class(food)

        return render_template(
            "recieve.html",
            foodsDonated=foodsDonated,
            today=today
        )




    if request.method == "POST":
        food_id = request.form.get("food_id")
        requested_qty = int(request.form.get("quantity"))
        user_email = session["user"]["email"]

        food = food_collection.find_one({"_id": ObjectId(food_id)})
        if not food:
            flash("Food item not found.", "danger")
            return redirect("/recieve")

        available_qty = int(food["quantity"])

        if requested_qty <= 0 or requested_qty > available_qty:
            flash("Invalid quantity requested.", "warning")
            return redirect("/recieve")

        # 1️⃣ Create requested food document
        requested_food = {
            "quantity": requested_qty,
            "food name": food["food name"],
            "expiration date": food["expiration date"],
            "name of donor": food["name of donor"],
            "date donated": food["date donated"],
            "shop name": food["shop name"],
            "status": "waiting for delivery driver",
            "requeststatus": "requested"
        }
        food_collection.insert_one(requested_food)

        # 2️⃣ Update remaining quantity
        remaining_qty = available_qty - requested_qty

        if remaining_qty == 0:
            food_collection.delete_one({"_id": ObjectId(food_id)})
        else:
            food_collection.update_one(
                {"_id": ObjectId(food_id)},
                {"$set": {"quantity": remaining_qty}}
            )

        # 3️⃣ Track recipient request
        request_record = {
            "food_name": food["food name"],
            "quantity": requested_qty,
            "shop_name": food["shop name"],
            "donor_name": food["name of donor"],
            "date_requested": date.today().strftime("%Y-%m-%d"),
            "status": "pending"
        }

        recipients_collection.update_one(
            {"email": user_email},
            {"$push": {"activerequests": request_record}}
        )

        flash("Food requested successfully 🍽️", "success")
        return redirect("/recieve")



    
@app.route("/pastdonations")
def pastdonations():
    foodsDonated = food_collection.find({
        "name of donor": session["user"]["full_name"],
        "status": "delivered"
    })
    return render_template("pastdonations.html", foodsDonated=foodsDonated)

    
@app.route("/pendingdonations")
def pendingdonations():
    foodsDonated = list(food_collection.find({
        "status": {"$ne": "delivered"}
    }))

    today = date.today()

    for food in foodsDonated:
        # Calculate expiration
        exp_date = datetime.strptime(food["expiration date"], "%Y-%m-%d").date()
        food["days_until_expiration"] = (exp_date - today).days

        # Auto-mark expired food
        if food["days_until_expiration"] < 0 and food["status"] != "delivered":
            food["status"] = "expired"
            food_collection.update_one(
                {"_id": food["_id"]},
                {"$set": {"status": "expired"}}
            )


        status = food["status"]
        if status == "waiting for delivery driver":
            food["status_class"] = "bg-secondary text-light"
        elif status == "driver coming":
            food["status_class"] = "bg-warning text-dark"
        elif status == "driver picked up food":
            food["status_class"] = "bg-info text-dark"
        elif status == "delivered":
            food["status_class"] = "bg-success text-light"
        elif status == "expired":
            food["status_class"] = "bg-danger text-light"
        else:
            food["status_class"] = "bg-secondary text-light"

    return render_template(
        "pendingdonations.html",
        foodsDonated=foodsDonated,
        today=today
    )


@app.route("/pickup", methods=["POST"])
def pickup_food():
    food_id = request.form.get("foodid")
    
    if not food_id:
        flash("Invalid food selection.", "danger")
        return redirect("/driver")

    food = food_collection.find_one({"_id": ObjectId(food_id)})
    if not food:
        flash("Food not found.", "danger")
        return redirect("/driver")
    print("1", food["status"])
    if food["status"] != "waiting for delivery driver":
        print("2")
        flash(f"Cannot pick up food. Current status: {food['status']}", "warning")
        return redirect("/pickupget")
    
    if food["requeststatus"] != "requested":
        print("2")
        flash(f"Cannot pickup up food. Current status: {food['requeststatus']}", "warning")
        return redirect("/pickupget")

    food_collection.update_one(
        {"_id": ObjectId(food_id)},
        {"$set": {"status": "driver coming"}}
    )
    flash("Pickup successful! 🚚", "success")
    return redirect("/pickupget")


@app.route("/confirmpickup", methods=["POST"])
def confirm_pickup():

    food_id = request.form.get("foodid")
    if not food_id:
        flash("Invalid food selection.", "danger")
        return redirect("/pickupget")

    food = food_collection.find_one({"_id": ObjectId(food_id)})
    if not food:
        flash("Food not found.", "danger")
        return redirect("/pickupget")

    if food["status"] != "driver coming" and food["status"] != "driver picked up food":
        flash(f"Cannot confirm delivery. Current status: {food['status']}", "warning")
        return redirect("/pickupget")

    if food["status"] == "driver picked up food":
        food_collection.update_one(
            {"_id": ObjectId(food_id)},
            {"$set": {"status": "delivered"}}
        )

    if food["status"] == "driver coming":
        food_collection.update_one(
            {"_id": ObjectId(food_id)},
            {"$set": {"status": "driver picked up food"}}
        )

    flash("Delivery confirmed ✅", "success")
    return redirect("/pickupget")

@app.route("/pickupget", methods=["GET"])
def pickup_page():
    foods = list(
    food_collection.find({
        "requeststatus": "requested",
        "status": {"$in": ["driver coming", "driver picked up food"]}
    })
)

    today = date.today()

    for food in foods:
        exp_date = datetime.strptime(food["expiration date"], "%Y-%m-%d").date()
        food["days_until_expiration"] = (exp_date - today).days
        # Assign status_class
        if food["status"] == "waiting for delivery driver":
            food["status_class"] = "bg-secondary text-light"
        elif food["status"] == "driver coming":
            food["status_class"] = "bg-danger text-dark"
        elif food["status"] == "driver picked up food":
            food["status_class"] = "bg-warning text-dark"
        elif food["status"] == "delivered":
            food["status_class"] = "bg-success text-light"
        else:
            food["status_class"] = "bg-danger text-light"

    return render_template("pickup.html", foodsDonated=foods, today=today)


if __name__ == "__main__":
    app.run(debug=True)