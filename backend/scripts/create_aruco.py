import cv2
import numpy as np

def generar_aruco(marker_id: int = 0, size_px: int = 800, out_path: str = "aruco_0.png"):
    # Diccionario ArUco (muy común y estable)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    # Genera el marker
    marker = cv2.aruco.generateImageMarker(aruco_dict, marker_id, size_px)

    # (Opcional) agregar margen blanco alrededor para mejor impresión/detección
    border = int(size_px * 0.15)
    canvas = 255 * np.ones((size_px + 2 * border, size_px + 2 * border), dtype=np.uint8)
    canvas[border:border + size_px, border:border + size_px] = marker

    cv2.imwrite(out_path, canvas)
    print(f"OK -> Guardado en: {out_path}")

if __name__ == "__main__":
    generar_aruco(marker_id=19, size_px=800, out_path="aruco_19.png")