import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import io
import numpy as np
from flask import Flask, render_template, Response
import base64
import time
from PIL import Image

app = Flask(__name__)

# Global frame buffer for thread-safe sharing
latest_frame = None
frame_width = 800
frame_height = 600

# Global color state
triangle_color = [0.0, 1.0, 0.0]  # Default green

def draw_triangle():
    glBegin(GL_TRIANGLES)
    glColor3f(*triangle_color)
    glVertex2f(-0.5, -0.5)
    glVertex2f(0.5, -0.5)
    glVertex2f(0.0, 0.5)
    glEnd()

def initialize_opengl(width, height):
    glClearColor(0.0, 0.0, 0.0, 1.0)  # Arka planı siyah yap
    glEnable(GL_DEPTH_TEST)
    gluPerspective(45, (width / height), 0.1, 50.0)  # Perspektif ayarı
    glTranslatef(0.0, 0.0, -5)  # Kamera konumu

import threading

# Global frame buffer
latest_frame = None
frame_width = 800
frame_height = 600

def opengl_loop():
    global latest_frame, triangle_color
    pygame.init()
    display = (frame_width, frame_height)
    pygame.display.set_mode(display, DOUBLEBUF | OPENGL)
    initialize_opengl(display[0], display[1])
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    triangle_color = [1.0, 0.0, 0.0]  # Red
                elif event.key == pygame.K_w:
                    triangle_color = [0.0, 1.0, 0.0]  # Green
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        draw_triangle()
        pygame.display.flip()
        # Frame capture
        glReadBuffer(GL_FRONT)
        pixels = glReadPixels(0, 0, frame_width, frame_height, GL_RGB, GL_UNSIGNED_BYTE)
        latest_frame = base64.b64encode(pixels).decode('utf-8')
        time.sleep(0.05)

@app.route('/')
def index():
    return render_template('index.html')  # HTML dosyanızın adı

@app.route('/key_event/<key>', methods=['POST'])
def key_event(key):
    global triangle_color
    if key == 'q':
        triangle_color = [1.0, 0.0, 0.0]  # Red
    elif key == 'w':
        triangle_color = [0.0, 1.0, 0.0]  # Green
    return '', 204

@app.route('/render_frame')
def render_frame():
    global latest_frame
    if latest_frame is None:
        return {'width': frame_width, 'height': frame_height, 'image': ''}
    return {'width': frame_width, 'height': frame_height, 'image': latest_frame}

if __name__ == '__main__':
    t = threading.Thread(target=opengl_loop, daemon=True)
    t.start()
    app.run(debug=True, use_reloader=False)


    # Ana döngü
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)  # Ekranı temizle
        draw_triangle()  # Üçgeni çiz
        pygame.display.flip()  # Ekranı güncelle
        time.sleep(0.01)  # FPS ayarı

        app.run(debug=True, use_reloader=False)
