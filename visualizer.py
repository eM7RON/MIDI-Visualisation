from collections import defaultdict 

import mido
import pygame
import pygame.gfxdraw
import math
import threading
import time
import sys

import constants as c
import spectrums

#from OpenGL.GL import *

# Get tempo from Mido midi-file
def get_tempo(midi_sequence):
    for msg in midi_sequence:
        if msg.type in {'note_on', 'note_off'} and msg.time:
            return 200000
        if msg.type == "set_tempo":
            return msg.tempo

def insert_intro(midi_sequence):
    global intro_time
    
    intro_ticks = round(mido.second2tick(intro_time, midi_sequence.ticks_per_beat, tempo))

    for trck in midi_sequence.tracks:
        trck.insert(0, mido.Message(type="note_off", velocity=0, time=intro_ticks))
        trck.insert(0, mido.MetaMessage(type="set_tempo", tempo=tempo))
        break

    return midi_sequence

# Convert note(0-127) to point coordinates on a circle(45° - 315°)
def circle_p(note, radius, mn, mx):
    
    angle = lo + note * hi#(mn - note) / (mx - mn)
    x = radius * math.cos(-angle * math.pi / 180.)
    y = radius * math.sin(angle * math.pi / 180.)
    rgb = cmap(angle)
    return round(x), round(y), rgb

# Convert all midi-messages to a list of points [note, 0, time note_on, time note_off]
# # The first two elements [note, 0, ..] are given to "set_coords" later, to convert them to circle coordinates.
# def convert_2_points(midi_sequence):

#     ret      = []
#     note_ons = []
#     tick     = 0
#     tempo    = 0
#     mx       = 0
#     mn       = 127

#     for msg in midi_sequence:

#         tick += msg.time

#         if msg.type == "set_tempo":
#             tempo = msg.tempo
#         elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
#             # end_point = [msg.note, 0, tick, 0]
#             for el in note_ons:
#                 if el[0] == msg.note:
#                     #[note x, note y, tick-on, tick_off]
#                     new_point = [msg.note, 0, el[2], tick]
#                     ret.append(new_point)
#                     note_ons.remove(el)

#         elif msg.type=="note_on" and msg.velocity > 0:
#             start_point = [msg.note, 0, tick, 1]
#             note_ons.append(start_point)
#             mx = max(msg.note, mx)
#             mn = min(msg.note, mn)

#     return ret, mn, mx

def compress_note_range(note_set):
    n_uniq   = len(note_set)
    notes    = sorted(note_set)
    note_map = {}
    for i in range(n_uniq):
        note_map[notes[i]] = i
    return note_map

# The first two elements [note, 0, ..] are given to "set_coords" later, to convert them to circle coordinates.
def convert_2_points(midi_sequence):

    ret        = []
    note_ons   = defaultdict(list)
    tick       = 0
    tempo      = 0
    mx         = -math.inf
    mn         = math.inf
    mx_inst    = -math.inf
    mn_inst    = math.inf
    mx_drum    = -math.inf
    spacer     = 1
    note_ticks = []
    inst_set   = set()
    drum_set   = set()
    drum_map   = {}

    for msg in midi_sequence:
        if msg.type in {'note_on', 'note_off'}:
            if msg.channel == 9:
                drum_set.add(c.DRUM_MAP[msg.note])
            else:
                mx_inst = max(msg.note, mx_inst)
                mn_inst = min(msg.note, mn_inst)
                inst_set.add(msg.note)
    
    drum_map = compress_note_range(drum_set)
    n_drum   = len(drum_set)
    inst_map = compress_note_range(inst_set)
    
    shift = n_drum + spacer - mn_inst

    mn_inst = math.inf

    for msg in midi_sequence:
        tick += msg.time

        if msg.type == 'set_tempo':
            tempo = msg.tempo
        elif msg.type in {'note_on', 'note_off'}:
     
            note = msg.note
            if msg.channel != 9:
                note = inst_map[note]
                note += shift
                mn_inst = min(note, mn_inst)
            else:
                note = drum_map[c.DRUM_MAP[note]]
                mx_drum = max(note, mx_drum)

            mx = max(note, mx)
            mn = min(note, mn)

            if msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                # end_point = [msg.note, 0, tick, 0]
                while note_ons[note]:
                    strt_tick = note_ons[note].pop()
                    ret.append([note, 0, strt_tick, tick])
                    duration = tick - strt_tick
                    for _ in range(round(duration)):
                        note_ticks.append(note)

            elif msg.type == 'note_on' and msg.velocity > 0:
                note_ons[note].append(tick)

    ret = [[1. - (x[0] - mn) / (mx - mn), *x[1: ]] for x in ret]

    return ret, mn, mx, avg

# Convert first two elements of the point-list to circle coordinates
def set_coords(msg_l, radius, mn, mx):
    for point in msg_l:
        x, y, rgb = circle_p(point[0], radius, mn, mx)
        point[: 2]  = x, y
        point.append(rgb)

# Create a list of circles to draw the inner moving circles. 1 circle every 5 seconds.
def spawn_circles(l):
    return [n for n in range(0, math.ceil(l) + 1, 5)]

# Playsthe midi-file. Sets the global variables "midi_time" (current time in seconds) and "midi_start" (True).
# This is probably not clean concurrent programming, but it works just fine so I kept it.
def play_midi(sequence, stop_event):

    global midi_time
    global midi_start

    if not midi_start:
        midi_start  = True
        midi_time = 0

    for msg in sequence:
        if msg.time:
            time.sleep(msg.time)
            midi_time += msg.time
        if not msg.is_meta:
            port.send(msg)
        if stop_event.is_set():
            return
    time.sleep(10)
    global running
    running = False
    

# Draws everything
def draw_screen(radius, midi_time, current_draw_time, prev_draw_time, msg_l, circles):

    global midi_start
    #global midi_time
    # start execution time
    start_t = time.time()
    # check for "new_midi" (midi_time) changed by the midi-playback. If true, take average time diff.
    if not midi_start:
        current_t = 0 #midi_time #prev_draw_time #intro_time
    elif prev_draw_time != midi_time:
        current_t = (current_draw_time + midi_time) / 2.
        prev_draw_time = midi_time
    else:
        current_t = current_draw_time

    # draw the center circle
    def draw_circle():
        pygame.gfxdraw.aacircle(screen,  center_x, center_y, radius + 4, (150, 150, 255, 128))

    # draw the moving inner circles according to time-step (current_t)
    def draw_inner_circles():
        for c in circles:
            z = d + c * scale - current_t * scale
            col = max(100, min(255 / (z / (d + 100)), 255))
            if z > 1:
                pygame.gfxdraw.circle(screen, center_x, center_y, round(radius / max((z / d), sys.float_info.epsilon)), (col, 0, col, 100))

    # draw the note-played effect
    def draw_effect(x, y):
        x_center_x = x + center_x
        y_center_y = y + center_y
        pygame.gfxdraw.aacircle(screen, x_center_x, y_center_y, 10, (55, 50, 10))
        pygame.draw.circle(screen, (200, 190, 10), (x_center_x, y_center_y), 3, 0)
        pygame.draw.circle(screen, (225, 200, 10), (x_center_x, y_center_y), 1, 0)

    # draw the red moving notes according to time-step (current_t)
    def draw_notes():
        for point in msg_l:
            x = point[0]
            y = point[1]
            z1 = (d + point[2] * scale) - current_t * scale
            z2 = (d + point[3] * scale) - current_t * scale
            z1d = max(z1 / d, sys.float_info.epsilon)
            z2d = max(z2 / d, sys.float_info.epsilon)
            x_p = round(x / z1d) + center_x
            y_p = round(y / z1d) + center_y
            p_width1 = max(1, min(round(15. / z1d), 35))
            p_width2 = max(1, min(round(15. / z2d), 35))
            col = max(0, min(200 / (z1 / (d + 100)), 255))
            x_p_end = round(x / z2d) + center_x
            y_p_end = round(y / z2d) + center_y

            z2int = round(z2)

            if z2int < d and z1 >= 1:
                pygame.draw.circle(screen, (60, 60, 60), (x_p_end, y_p_end), p_width2, 1)
                pygame.draw.line(screen, (60, 60, 60), (x_p, y_p), (x_p_end, y_p_end), 2)
                pygame.draw.circle(screen, (60, 60, 60), (x_p, y_p), p_width1, 0)

            elif round(z1) <= d <= z2int:
                pygame.gfxdraw.aacircle(screen,  center_x, center_y, radius + 5, (0, 0, 120))
                pygame.draw.circle(screen, point[-1], (x_p_end, y_p_end), p_width2, 1)
                if z1 < 1:
                    pygame.draw.line(screen, point[-1], (x / 0.2 + center_x, y / 0.2 + center_y), (x_p_end, y_p_end), 15)
                else:
                    pygame.draw.line(screen, point[-1], (x_p, y_p), (x_p_end, y_p_end), 15)

                if z1 >= 1:
                    pygame.draw.circle(screen, point[-1], (x_p, y_p), p_width1, 0)
                draw_effect(x, y)

            elif z1 >= 1:
                pygame.draw.circle(screen, (col, col, col), (x_p_end, y_p_end), p_width2, 1)
                pygame.draw.line(screen, (col, col, col), (x_p, y_p), (x_p_end, y_p_end), 2)
                pygame.draw.circle(screen, (col, col, col), (x_p, y_p), p_width1, 0)

    
    #draw_circle()
    if midi_start:
        draw_notes()
        draw_circle()
        draw_inner_circles()

        ret = current_t + time.time() - start_t, prev_draw_time
    else:
        ret = current_t, current_t
    return ret


if __name__ == '__main__':

    if not 1 < len(sys.argv) <= 4:
        print('Incorrect number of args. Please provide path to midi file only.', end='')
        sys.exit()

    pygame.init()
    
    if '-s' in sys.argv:
        s = int(sys.argv[sys.argv.index('-s') + 1])
    else:
        s = -1
    spectrum = spectrums.get_spectrum(s)
    n_rgb    = len(spectrum)

    lo = -45
    hi = 225
    d     = 100
    scale = 35
    intro_time  = 0 # seconds
    midi_time = 0
    midi_start  = False
    fullscreen  = True
    running     = True

    cmap = lambda x: spectrum[round(((x - lo) / (hi - lo)) * n_rgb)]


    # read and prepare midi-file. CHANGE FILENAME HERE.
    port = mido.open_output()
    midi_sequence = mido.MidiFile(sys.argv[1])
    # add a start delay to put all notes further back
    tempo = get_tempo(midi_sequence)

    midi_sequence = insert_intro(midi_sequence)

    # convert to point list
    msg_l, mn, mx, avg = convert_2_points(midi_sequence)

    # init pygame screen

    screen_info = pygame.display.Info()
    screen_size = (width, height) = (screen_info.current_w, screen_info.current_h)
    screen      = pygame.display.set_mode(screen_size, flags=pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF)
    pygame.display.set_caption("MIDI Visualizer")
    center_x = round(width / 2.)
    center_y = round(height / 2.)
    smallest_dimension = min(height, width)
    radius   = round((smallest_dimension - 0.4167 * smallest_dimension) / 2.)

    set_coords(msg_l, radius, mn, mx)
    circles = spawn_circles(midi_sequence.length)

    current_draw_time, prev_draw_time = draw_screen(radius, midi_time, midi_time, midi_time - 1e-3, msg_l, circles)

    # play midi-file in a concurrent thread
    t1_stop = threading.Event()
    t1 = threading.Thread(target=play_midi, args=[midi_sequence, t1_stop])
    t1.start()
    # main visualisation loop

    while running:
        for event in pygame.event.get():
            if event.type is pygame.KEYDOWN:
                if fullscreen and event.key == pygame.K_ESCAPE:
                    pygame.display.set_mode(screen_size, flags=pygame.RESIZABLE | pygame.HWSURFACE | pygame.DOUBLEBUF)
                    fullscreen = False
                elif not fullscreen and event.key == pygame.K_f:
                    pygame.display.set_mode(screen_size, flags=pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF)
                    fullscreen = True
            elif event.type == pygame.QUIT:
                running = False

        screen.fill(c.BLACK)
        current_draw_time, prev_draw_time = draw_screen(radius, midi_time, current_draw_time, prev_draw_time, msg_l, circles)
        pygame.display.update()

    t1_stop.set()
    pygame.quit()
    sys.exit()