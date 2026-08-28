from ultralytics import YOLO
model = YOLO("WTbest.pt")
model.predict(source="Checkpost surveillance/WTbest.pt", show=True, conf=0.30
,save=True,project="Checkpost surveillance/outputs",name="test_run2" )