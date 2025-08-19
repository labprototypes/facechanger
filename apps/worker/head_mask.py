import os
import cv2
import numpy as np
from typing import Optional, Tuple, Dict

# Optional YOLO (person detection improves back-facing cases)
try:
    from ultralytics import YOLO  # type: ignore
    _YOLO_PERSON_MODEL = os.environ.get("HEAD_YOLO_MODEL", "yolov8n.pt")
    _YOLO_PERSON = YOLO(_YOLO_PERSON_MODEL)
except Exception:
    _YOLO_PERSON = None

MARGIN = float(os.environ.get("HEAD_MASK_MARGIN", "0.30"))
MIN_SIZE = int(os.environ.get("HEAD_MASK_MIN_SIZE", "0"))
HEAD_RATIO = float(os.environ.get("HEAD_FROM_BODY_RATIO", "0.20"))
PERSON_WIDTH_SCALE = float(os.environ.get("HEAD_PERSON_WIDTH_SCALE", "0.55"))  # how much of person width to use for head square side baseline
PERSON_HEAD_TOP_FRAC = float(os.environ.get("HEAD_PERSON_HEAD_TOP_FRAC", "0.23"))  # fraction of person height where bottom of head square roughly ends (shoulder line)
PERSON_EXTRA_UP_FRAC = float(os.environ.get("HEAD_PERSON_EXTRA_UP_FRAC", "0.15"))  # extend upward above computed head square

# Optional mediapipe pose (graceful fallback)
try:
    import mediapipe as mp  # type: ignore
    _MP_POSE = mp.solutions.pose.Pose(static_image_mode=True)
except Exception:
    _MP_POSE = None

def _load_image(path: str):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Cannot read image: {path}")
    return img

def _detect_face_box(img) -> Optional[Tuple[int,int,int,int]]:
    h, w = img.shape[:2]
    modelFile = "res10_300x300_ssd_iter_140000_fp16.caffemodel"
    protoFile = "deploy.prototxt"
    if os.path.exists(modelFile) and os.path.exists(protoFile):
        try:
            net = cv2.dnn.readNetFromCaffe(protoFile, modelFile)
            blob = cv2.dnn.blobFromImage(cv2.resize(img, (300,300)), 1.0, (300,300), (104,117,123))
            net.setInput(blob)
            det = net.forward()
            best=None; best_conf=0
            for i in range(det.shape[2]):
                conf = float(det[0,0,i,2])
                if conf < 0.4: continue
                x1 = int(det[0,0,i,3]*w); y1 = int(det[0,0,i,4]*h)
                x2 = int(det[0,0,i,5]*w); y2 = int(det[0,0,i,6]*h)
                if x2<=x1 or y2<=y1: continue
                if conf>best_conf:
                    best=(x1,y1,x2,y2); best_conf=conf
            if best:
                return best
        except Exception:
            pass
    # Haar fallback
    try:
        haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = haar.detectMultiScale(gray, 1.1, 4)
        if len(faces)==0:
            return None
        x,y,wf,hf = max(faces, key=lambda b: b[2]*b[3])
        return (int(x),int(y),int(x+wf),int(y+hf))
    except Exception:
        return None

def _detect_pose_head_box(img) -> Optional[Tuple[int,int,int,int]]:
    if _MP_POSE is None:
        return None
    h,w = img.shape[:2]
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    res = _MP_POSE.process(rgb)
    if not res.pose_landmarks:
        return None
    lm = res.pose_landmarks.landmark
    idxs = [0,1,2,7,8]
    pts=[]
    for i in idxs:
        if i < len(lm) and lm[i].visibility > 0.25:
            pts.append((int(lm[i].x*w), int(lm[i].y*h)))
    if not pts:
        shoulders=[]
        for i in [11,12]:
            if i < len(lm) and lm[i].visibility > 0.25:
                shoulders.append((int(lm[i].x*w), int(lm[i].y*h)))
        if not shoulders:
            return None
        if len(shoulders)==2:
            sx = (shoulders[0][0]+shoulders[1][0])//2
            sy = (shoulders[0][1]+shoulders[1][1])//2
            sw = abs(shoulders[0][0]-shoulders[1][0])
        else:
            sx, sy = shoulders[0]
            sw = int(w*0.25)
        side = int(sw*0.9)
        x1 = sx - side//2
        y1 = sy - int(side*1.1)
        return (x1,y1,x1+side,y1+side)
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    x1=min(xs); x2=max(xs); y1=min(ys); y2=max(ys)
    if (y2 - y1) < 10:
        y2 = y1 + (x2-x1)
    return (x1,y1,x2,y2)

def _detect_person_box(img)->Optional[Tuple[int,int,int,int]]:
    # YOLO first (works for back views)
    if _YOLO_PERSON is not None and os.environ.get("HEAD_USE_YOLO", "1") == "1":
        try:
            res = _YOLO_PERSON(img, verbose=False)
            best=None; best_conf=0.0
            for r in res:
                if not getattr(r, 'boxes', None):
                    continue
                for b in r.boxes:
                    cls = int(b.cls.item()) if hasattr(b.cls, 'item') else int(b.cls)
                    if cls != 0:  # class 0 = person
                        continue
                    conf = float(b.conf.item()) if hasattr(b.conf, 'item') else float(b.conf)
                    if conf < float(os.environ.get("HEAD_PERSON_CONF", "0.35")):
                        continue
                    x1,y1,x2,y2 = map(int, b.xyxy[0].tolist())
                    if x2<=x1 or y2<=y1: continue
                    area = (x2-x1)*(y2-y1)
                    if conf > best_conf or (conf == best_conf and best and area > (best[2]-best[0])*(best[3]-best[1])):
                        best=(x1,y1,x2,y2); best_conf=conf
            if best:
                return best
        except Exception:
            pass
    # HOG fallback
    try:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        rects,_ = hog.detectMultiScale(img, winStride=(8,8))
        if len(rects)==0:
            return None
        x,y,wf,hf = max(rects, key=lambda r: r[2]*r[3])
        return (int(x),int(y),int(x+wf),int(y+hf))
    except Exception:
        return None

def _square_with_margin(box, shape):
    h,w = shape[:2]
    x1,y1,x2,y2 = box
    bw = x2-x1; bh=y2-y1
    dw = int(bw*MARGIN); dh=int(bh*MARGIN)
    x1 -= dw; x2 += dw; y1 -= dh; y2 += dh
    bw = x2-x1; bh=y2-y1
    side = max(bw, bh, MIN_SIZE)
    cx = (x1+x2)//2; cy=(y1+y2)//2
    x1 = cx - side//2; y1 = cy - side//2
    x2 = x1 + side; y2 = y1 + side
    if x1 < 0: x2 += -x1; x1=0
    if y1 < 0: y2 += -y1; y1=0
    if x2 > w: shift = x2-w; x1 -= shift; x2=w
    if y2 > h: shift = y2-h; y1 -= shift; y2=h
    x1=max(0,x1); y1=max(0,y1)
    return (x1,y1,x2,y2)

def _build_mask(shape, box):
    h,w = shape[:2]
    m = np.zeros((h,w), dtype=np.uint8)
    x1,y1,x2,y2 = box
    m[y1:y2, x1:x2] = 255
    return m

def generate_head_mask_auto(image_path: str, out_mask_path: str):
    img = _load_image(image_path)
    face = _detect_face_box(img)
    if face:
        sq = _square_with_margin(face, img.shape)
        mask = _build_mask(img.shape, sq); cv2.imwrite(out_mask_path, mask)
        return {"strategy":"face","box":sq}, out_mask_path
    pose = _detect_pose_head_box(img)
    if pose:
        sq = _square_with_margin(pose, img.shape)
        mask = _build_mask(img.shape, sq); cv2.imwrite(out_mask_path, mask)
        return {"strategy":"pose","box":sq}, out_mask_path
    person = _detect_person_box(img)
    if person:
        x1,y1,x2,y2 = person
        pw = max(1, x2 - x1)
        ph = max(1, y2 - y1)
        # Heuristic shoulders/back: define a square whose bottom lies near PERSON_HEAD_TOP_FRAC of person height
        head_bottom = y1 + int(ph * PERSON_HEAD_TOP_FRAC)
        side_from_width = int(pw * PERSON_WIDTH_SCALE)
        side_from_height = int(ph * HEAD_RATIO)
        side = max(32, side_from_width, side_from_height)
        # center horizontally within person box
        cx = x1 + pw // 2
        y2h = head_bottom
        y1h = y2h - side
        # add extra upward extension (back hair) if space
        extra_up = int(side * PERSON_EXTRA_UP_FRAC)
        y1h = max(0, y1h - extra_up)
        # clamp
        if y1h < 0:
            y1h = 0
            y2h = y1h + side
        head_box = (cx - side//2, y1h, cx - side//2 + side, y2h)
        sq = _square_with_margin(head_box, img.shape)
        mask = _build_mask(img.shape, sq); cv2.imwrite(out_mask_path, mask)
        return {"strategy":"person-shoulders","box":sq}, out_mask_path
    h,w = img.shape[:2]
    side = int(min(h,w)*0.5)
    cx, cy = w//2, int(h*0.35)
    fallback = (cx-side//2, cy-side//2, cx+side//2, cy+side//2)
    sq = _square_with_margin(fallback, img.shape)
    mask = _build_mask(img.shape, sq); cv2.imwrite(out_mask_path, mask)
    return {"strategy":"center","box":sq}, out_mask_path
