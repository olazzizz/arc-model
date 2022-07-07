import tensorflow as tf
import numpy as np
import base64
from pickle import dump, load
import sklearn
from datetime import datetime

model_dir = "models/openimages_v4_ssd_mobilenet_v2_1"
saved_model = tf.saved_model.load(model_dir)
detector = saved_model.signatures["default"]

# the list of categories of items and their max stock 
categories = {"Bottle": 100,
              "Pen":1000,
              "Footwear":50,
              "Drink":100,
              "Clothing":500}


"""
load the models necessary to predict discounts.
"""
def load_discount_model():
    discounts_path = 'calculate-discounts/discount_models'
    model = load(open(discounts_path+'/knn-model_0.pkl', 'rb'))
    sc = load(open(discounts_path+'/scaler_0.pkl', 'rb'))
    enc = load(open(discounts_path+'/label-encoder_0.pkl', 'rb'))
    return model, sc, enc


disc_model, scaler, encoder = load_discount_model()

def predict(body):
    base64img = body.get("image")
    img_bytes = base64.decodebytes(base64img.encode())

    # img_bytes = tf.io.read_file("images/RHODS_cool_store.png")
    # img_bytes = base64.decodebytes(base64img.encode())

    detections = detect(img_bytes)
    cleaned = clean_detections(detections)

    discs = predict_discounts(cleaned)

    return {"detections": discs}


"""
predict discounts for each item
based on 'current stock'
"""
def predict_discounts(cleaned):
    # get current stock, convert to np array
    current_stock = find_stock()
    list_stock = list(current_stock.items())
    stock_array = np.asarray(list_stock)

    # store both columns of np array
    orig_labels = stock_array[:,0]
    stock = stock_array[:,1]

    # encode labels, apply scaler
    labels = encoder.transform(orig_labels)
    stock_array = np.column_stack((labels,stock))
    stock_array = scaler.transform(stock_array)

    # make model predictions on scaled data
    predictions = disc_model.predict(stock_array)
    print(predictions)

    labels_preds = dict(zip(orig_labels, predictions))
    print(labels_preds)

    for detection in cleaned:
        detected_discount = labels_preds[detection['class']]
        print(detected_discount)

    return cleaned


"""
find the current stock of items
based on the current time of day
"""
def find_stock():
    # ref for calc of seconds_since_midnight: https://stackoverflow.com/a/15971505
    now = datetime.now()
    seconds_since_midnight = (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
    portion_of_day = seconds_since_midnight / 86400  # fraction of day at this time.

    # multiply all categories max stock by the portion of the daytime
    stock_items = categories.copy()
    stock_items.update((x, int((y*portion_of_day))) for x,y in stock_items.items())

    return stock_items


def detect(img):
    image = tf.image.decode_jpeg(img, channels=3)
    converted_img = tf.image.convert_image_dtype(image, tf.float32)[tf.newaxis, ...]
    result = detector(converted_img)
    num_detections = len(result["detection_scores"])

    output_dict = {key: value.numpy().tolist() for key, value in result.items()}
    output_dict["num_detections"] = num_detections

    return output_dict


def clean_detections(detections):
    cleaned = []
    max_boxes = 10
    num_detections = min(detections["num_detections"], max_boxes)

    # hard code coupon value to 0.15 and only include detected classes in our list.
    for i in range(0, num_detections):
        d = {
            "box": {
                "yMin": detections["detection_boxes"][i][0],
                "xMin": detections["detection_boxes"][i][1],
                "yMax": detections["detection_boxes"][i][2],
                "xMax": detections["detection_boxes"][i][3],
            },
            "class": detections["detection_class_entities"][i].decode("utf-8"),
            "cValue": "15% off",
            "label": detections["detection_class_entities"][i].decode("utf-8"),
            "score": detections["detection_scores"][i],
        }
        if d.get("class") in categories.keys() and d.get("score") >= 0.15:
            cleaned.append(d)

    return cleaned


"""
This is to 'warm up' the model.
"""
def preload_model():
    blank_jpg = tf.io.read_file("blank.jpeg")
    blank_img = tf.image.decode_jpeg(blank_jpg, channels=3)
    detector(tf.image.convert_image_dtype(blank_img, tf.float32)[tf.newaxis, ...])


preload_model()
# detections = predict()
# print(detections)
