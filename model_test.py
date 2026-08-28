from ultralytics import YOLO
model = YOLO("WTbest.pt")
model.predict(source="test-input/15396176_1920_1080_25fps.mp4", show=True, conf=0.30
,save=True,project="/Users/ak_junior/Desktop/Nexus-Garuda/outputs",name="test_run2" )