import mido
import pygame
import pygame.gfxdraw
import math
import threading
import time
import sys
import spectrums

RGB   = spectrums.get_spectrum(-1)
n_RGB = len(RGB)


inner_cmap = {}
i = 0
for j in range(0, n_RGB * 3, 3):
    for k in range(j, j + 3):
        inner_cmap[k] = i
    i += 1
        
m_RGB = n_RGB * 3 / 500
outer_cmap = lambda x: round(x * m_RGB)
CMAP = lambda x: RGB[inner_cmap[outer_cmap(round(x))]]

WHITE = 255, 255, 255
BLACK = 0, 0, 0
RED   = 255, 0, 0
GREEN = 0, 255, 0
BLUE  = 0, 0, 255

# Get tempo from Mido midi-file
def getTempo(midi_file):

    tempo = 0
    for msg in midi_file:
        if msg.type=="set_tempo":
            tempo = msg.tempo
            break
    return tempo

# Convert note(0-127) to point coordinates on a circle(45° - 315°)
def circle_p(note, radius, mn, mx):

    angle = 135. - ((mn - note) / (mx - mn)) * 270.
    x = radius * math.cos(-angle * math.pi / 180.)
    y = radius * math.sin(-angle * math.pi / 180.)
    rgb = CMAP(angle)
    return round(x), round(y), rgb

# Convert all midi-messages to a list of points [note, 0, time note_on, time note_off]
# The first two elements [note, 0, ..] are given to "set_coords" later, to convert them to circle coordinates.
def convert_2_points(midi_file):

    ret      = []
    note_ons = []
    pos      = 0
    tempo    = 0
    mx       = 0
    mn       = 127
    for msg in midi_file:
        if msg.type == "set_tempo":
            tempo = msg.tempo
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            msg_s = msg.time
            pos += msg_s
            end_point = [msg.note, 0, pos, 0]
            for el in note_ons:
                if el[0] == msg.note:
                    #[note x, note y, pos-on, pos_off]
                    new_point = [msg.note, 0, el[2], pos]
                    ret.append(new_point)
                    note_ons.remove(el)

        elif msg.type=="note_on" and msg.velocity > 0:
            msg_s = msg.time
            pos += msg_s
            start_point = [msg.note, 0, pos, 1]
            note_ons.append(start_point)
            mx = max(msg.note, mx)
            mn = min(msg.note, mn)
        else:
            msg_s = msg.time
            pos += msg_s

    return ret, tempo, mn, mx

# Convert first two elements of the point-list to circle coordinates
def set_coords(msg_l, radius, mn, mx):
    for point in msg_l:
        x, y, rgb = circle_p(point[0], radius, mn, mx)
        point[: 2]  = x, y
        point.append(rgb)

# Create a list of circles to draw the inner moving circles. 1 circle every 5 seconds.
def spawn_circles(l):
    return [n for n in range(0, math.ceil(l) + 1, 5)]

# Playsthe midi-file. Sets the global variables "global_t" (current time in seconds) and "midi_start" (True).
# This is probably not clean concurrent programming, but it works just fine so I kept it.
def play_midi(sequence, stop_event):

    global global_t
    global midi_start

    if not midi_start:
        midi_start = True
        global_t = 0

    for msg in sequence:
        wait_t = msg.time
        time.sleep(wait_t)
        if not msg.is_meta:
            port.send(msg)
        global_t += msg.time
        if stop_event.is_set():
            return #break

# Draws everything
def draw_screen(screen, width, height, radius, old_midi_t, new_midi_t, cur_t, msg_l, circles):

    global midi_start
    # start execution time
    start_t = time.time()
    # check for "new_midi" (global_t) changed by the midi-playback. If true, take average time diff.
    if not midi_start:
        current_t = 0
    elif old_midi_t != new_midi_t:
        current_t = (cur_t + new_midi_t) / 2
        old_midi_t = new_midi_t
    else:
        current_t = cur_t

    d     = 100
    scale = 25

    # draw the center circle
    def draw_circle():	
        pygame.gfxdraw.aacircle(screen,  center_x, center_y, radius + 4, (150, 150, 255))

    # draw the moving inner circles according to time-step (current_t)
    def draw_inner_circles():
        for c in circles:
            z = d + c * scale - current_t * scale
            col = max(100, min(255 / (z / (d + 100)), 255))
            if z > 1:
                pygame.gfxdraw.circle(screen, center_x, center_y, round(radius / (z / d)), (col, 0, col, 100))

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
            z1d = z1 / d
            z2d = z2 / d
            x_p = round(x / z1d) + center_x
            y_p = round(y / z1d) + center_y
            p_width1 = max(1, min(round(15. / z1d), 35))
            p_width2 = max(1, min(round(15. / z2d), 35))
            col = max(0, min(200 / (z1 / (d + 100)), 255))
            # gcol = max(0, min(200 / (z1 / (d + 100)), 255))
            # bcol = max(0, min(200 / (z1 / (d + 100)), 255))
            x_p_end = round(x / z2d) + center_x
            y_p_end = round(y / z2d) + center_y

            if round(z2) < d and z1 >= 1:
                pygame.draw.circle(screen, (60, 60, 60), (x_p_end, y_p_end), p_width2, 1)				
                pygame.draw.line(screen, (60, 60, 60), (x_p, y_p), (x_p_end, y_p_end), 2)
                pygame.draw.circle(screen, (60, 60, 60), (x_p, y_p), p_width1, 0)	

            elif round(z1) <= d <= round(z2):
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

    draw_inner_circles()
    draw_circle()
    draw_notes()
    pygame.display.update()

    # return exec-time and the latest midi time-stamp
    return current_t + time.time() - start_t, old_midi_t


if __name__ == '__main__':

    # read and prepare midi-file. CHANGE FILENAME HERE.
    port = mido.open_output()
    mid = mido.MidiFile(sys.argv[1])
    # add a start delay to put all notes further back
    tempo = getTempo(mid)
    for trks in mid.tracks:
        trks.insert(0, mido.Message(type="note_off", velocity=0, time=round(mido.second2tick(3, mid.ticks_per_beat, tempo))))
        trks.insert(0, mido.MetaMessage(type="set_tempo", tempo=tempo))
    mid.save("preprocessed.mid")
    pp = mido.MidiFile('preprocessed.mid')
    # convert to point list
    msg_l, tempo2, mn, mx = convert_2_points(pp)
    print(type(msg_l))
    # init pygame screen
    pygame.init()

    screen_info   = pygame.display.Info()
    width, height = screen_info.current_w, screen_info.current_h
    screen_size   = (width, height) = (1920, 1080)
    screen        = pygame.display.set_mode(screen_size, pygame.FULLSCREEN)#, pygame.HWSURFACE)
    screen_modes  = pygame.display.list_modes()
    fullscreen    = True
    pygame.display.set_caption("MIDI Visualizer")
    center_x = round(width / 2)
    center_y = round(height / 2)
    min_dimension = min(height, width)
    radius = round((min_dimension - 0.4167 * min_dimension ) / 2)

    set_coords(msg_l, radius, mn, mx)
    circles = spawn_circles(pp.length)

    midi_start = False
    global_t = 0
    draw_t, old_t = draw_screen(screen, width, height, radius, -1, global_t, 0, msg_l, circles)

    # play midi-file in a concurrent thread
    t1_stop = threading.Event()
    t1 = threading.Thread(target=play_midi, args=[pp, t1_stop])
    t1.start()
    # main visualisation loop
    running = True
    while running:
        for event in pygame.event.get():
            if event.type is pygame.KEYDOWN:
                if fullscreen and event.key == pygame.K_ESCAPE:
                    pygame.display.set_mode(screen_size, pygame.RESIZABLE)
                    fullscreen = False
                elif not fullscreen and event.key == pygame.K_f:
                    pygame.display.set_mode(screen_size, pygame.FULLSCREEN) #pygame.display.set_mode(screen_size, pygame.FULLSCREEN)
                    fullscreen = True
            elif event.type == pygame.QUIT:
                running = False

        screen.fill(BLACK)
        draw_t, old_t = draw_screen(screen, width, height, radius, old_t, global_t, draw_t, msg_l, circles)
        pygame.display.update()

    t1_stop.set()
    pygame.quit()
    sys.exit()