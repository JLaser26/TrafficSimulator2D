#!/usr/bin/env python3
# simulator.py — Final Stable Version with Intersection Reservation System
import sys, json, random, math, os
import pygame
from pygame.math import Vector2
from map_utils import load_map_data, build_graph, find_path

SCREEN_W, SCREEN_H = 1000, 700
BG = (200, 220, 230)
ROAD_COLOR = (40, 40, 40)
LANE_COLOR = (70, 70, 70)
HUB_COLOR = (255, 200, 0)
CAR_COLOR = (30, 60, 200)
LIGHT_GREEN = (0, 200, 0)
LIGHT_RED = (200, 0, 0)

# ------------------------------------------------------------
class TrafficLight:
    def __init__(self, data):
        self.x = data['x']
        self.y = data['y']
        self.green = data.get('green', 6)
        self.red = data.get('red', 6)
        self.offset = data.get('offset', 0)
        self.t = self.offset

    def update(self, dt):
        self.t += dt

    def is_green_for(self, dir_vec):
        """Alternating horizontal/vertical green phase."""
        cycle = self.green + self.red
        phase = (self.t % cycle)
        horizontal = abs(dir_vec.x) > abs(dir_vec.y)
        if horizontal:
            # horizontal cars move first
            return phase < self.green
        else:
            # vertical cars move next
            return phase >= self.green


# ------------------------------------------------------------
class Car:
    def __init__(self, path_nodes, nodes, sim, cid):
        self.path = path_nodes
        self.nodes = nodes
        self.sim = sim
        self.id = cid
        self.edge_idx = 0
        self.progress = 0.0
        self.speed = 80 + random.uniform(-15, 15)
        self.radius = 6
        self.finished = False
        self.intersection_target = None
        if self.path:
            self.pos = Vector2(self.nodes[self.path[0]])
        else:
            self.pos = Vector2(0, 0)

    def current_edge(self):
        if self.edge_idx + 1 < len(self.path):
            return (self.path[self.edge_idx], self.path[self.edge_idx + 1])
        return None

    def update(self, dt):
        if self.finished:
            return
        if self.edge_idx + 1 >= len(self.path):
            self.finished = True
            return

        a = Vector2(self.nodes[self.path[self.edge_idx]])
        b = Vector2(self.nodes[self.path[self.edge_idx + 1]])
        edge_vec = b - a
        edge_len = edge_vec.length() if edge_vec.length() != 0 else 1
        dir_vec = edge_vec.normalize()
        road_type = self.sim.get_edge_type((self.path[self.edge_idx], self.path[self.edge_idx + 1]))

        # Maintain spacing
        leader = None
        min_gap = 1e9
        for other in self.sim.cars:
            if other is self or other.finished:
                continue
            rel = other.pos - self.pos
            dist = rel.length()
            if dist < 25 and rel.dot(dir_vec) > 0:
                if dist < min_gap:
                    min_gap = dist
                    leader = other
        max_speed = self.speed
        if leader and min_gap < 18:
            max_speed = 0
        elif leader and min_gap < 40:
            max_speed = min(max_speed, self.speed * 0.5)

        # --- Traffic light + intersection reservation ---
        for lt in self.sim.lights:
            light_pos = Vector2(lt.x, lt.y)
            to_light = light_pos - self.pos
            dist = to_light.length()
            if dist < 80 and to_light.dot(dir_vec) > 0:
                stop_point = light_pos - dir_vec * 25

                # if light red for this direction
                if not lt.is_green_for(dir_vec):
                    if (stop_point - self.pos).length() < 35:
                        max_speed = 0
                # check intersection reservation
                if lt in self.sim.occupied and self.sim.occupied[lt] != self:
                    if (light_pos - self.pos).length() < 60:
                        max_speed = 0
                # Reserve intersection if approaching & light green
                if lt.is_green_for(dir_vec) and (light_pos - self.pos).length() < 40:
                    self.sim.occupied[lt] = self
                    self.intersection_target = lt

        # Release intersection after passing
        if self.intersection_target:
            light_pos = Vector2(self.intersection_target.x, self.intersection_target.y)
            if (self.pos - light_pos).length() > 60:
                if self.sim.occupied.get(self.intersection_target) == self:
                    self.sim.occupied.pop(self.intersection_target, None)
                self.intersection_target = None

        # --- Symbol handling ---
        for s in self.sim.symbols:
            sym_vec = Vector2(s['x'], s['y']) - self.pos
            dist = sym_vec.length()
            if s.get('type') == 'slow' and dist < 50:
                max_speed = min(max_speed, 40)
            elif s.get('type') == 'no_entry' and sym_vec.dot(dir_vec) > 0 and dist < 50:
                return

        # Move
        move = max_speed * dt
        delta_progress = move / edge_len
        self.progress += delta_progress
        if self.progress >= 1.0:
            self.edge_idx += 1
            if self.edge_idx + 1 >= len(self.path):
                self.pos = Vector2(self.nodes[self.path[-1]])
                self.finished = True
                return
            self.progress = 0.0
            a = Vector2(self.nodes[self.path[self.edge_idx]])
            self.pos = a
        else:
            lane_offset = Vector2(0, 0)
            if road_type == 'big':
                perp = Vector2(-dir_vec.y, dir_vec.x)
                if abs(dir_vec.x) >= abs(dir_vec.y):
                    lane_offset = perp * (5 if dir_vec.x > 0 else -5)
                else:
                    lane_offset = perp * (5 if dir_vec.y > 0 else -5)
            self.pos = a + dir_vec * (self.progress * edge_len) + lane_offset

    def draw(self, surf):
        pygame.draw.circle(surf, CAR_COLOR, (int(self.pos.x), int(self.pos.y)), self.radius)


# ------------------------------------------------------------
class Simulator:
    def __init__(self, mapfile):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption('Traffic Simulator - Intersection Reservation')
        self.clock = pygame.time.Clock()
        self.map = load_map_data(mapfile)
        self.nodes, self.edges = build_graph(self.map)
        self.lights = [TrafficLight(l) for l in self.map.get('lights', [])]
        self.symbols = self.map.get('symbols', [])
        self.cars = []
        self.next_car_id = 1
        self.spawn_mode = False
        self.spawn_click = []
        self.occupied = {}  # intersection reservation {TrafficLight: Car}

    def get_edge_type(self, edge):
        for r in self.map.get('roads', []):
            rid = r['id']
            if f"r{rid}_" in str(edge[0]) or f"r{rid}_" in str(edge[1]):
                return r.get('type', 'small')
        return 'small'

    def spawn_car(self, start_id, end_id):
        path = find_path(self.edges, start_id, end_id, traffic_counts=None)
        if not path or len(path) < 2:
            return False
        car = Car(path, self.nodes, self, self.next_car_id)
        self.next_car_id += 1
        self.cars.append(car)
        return True

    def update(self, dt):
        for lt in self.lights:
            lt.update(dt)
        for car in list(self.cars):
            car.update(dt)
            if car.finished:
                self.cars.remove(car)

    def draw(self):
        self.screen.fill(BG)
        for r in self.map.get('roads', []):
            pygame.draw.rect(self.screen, ROAD_COLOR, (r['x'], r['y'], r['w'], r['h']))
            if r.get('type') == 'big':
                if r['w'] >= r['h']:
                    y_mid = r['y'] + r['h'] / 2
                    pygame.draw.line(self.screen, LANE_COLOR, (r['x'], y_mid), (r['x'] + r['w'], y_mid), 2)
                else:
                    x_mid = r['x'] + r['w'] / 2
                    pygame.draw.line(self.screen, LANE_COLOR, (x_mid, r['y']), (x_mid, r['y'] + r['h']), 2)

        for h in self.map.get('hubs', []):
            pygame.draw.circle(self.screen, HUB_COLOR, (int(h['x']), int(h['y'])), 12)
            font = pygame.font.SysFont(None, 18)
            txt = font.render(h.get('name', ''), True, (0, 0, 0))
            self.screen.blit(txt, (h['x'] - txt.get_width() / 2, h['y'] - 25))

        for lt in self.lights:
            col = LIGHT_GREEN if lt.t % (lt.green + lt.red) < lt.green else LIGHT_RED
            pygame.draw.circle(self.screen, col, (int(lt.x), int(lt.y)), 8)

        for s in self.symbols:
            if s.get('type') == 'slow':
                pygame.draw.rect(self.screen, (150, 150, 150), (s['x'] - 10, s['y'] - 6, 20, 12))
            elif s.get('type') == 'no_entry':
                pygame.draw.circle(self.screen, (220, 50, 50), (int(s['x']), int(s['y'])), 8)
                pygame.draw.line(self.screen, (255, 255, 255),
                                 (s['x'] - 5, s['y']), (s['x'] + 5, s['y']), 2)

        for c in self.cars:
            c.draw(self.screen)

        font = pygame.font.SysFont(None, 20)
        txt = font.render(f"Spawn(S): {'ON' if self.spawn_mode else 'OFF'}  Cars: {len(self.cars)}", True, (0, 0, 0))
        self.screen.blit(txt, (10, 10))
        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_s:
                    self.spawn_mode = not self.spawn_mode
                elif e.type == pygame.MOUSEBUTTONDOWN and self.spawn_mode:
                    x, y = e.pos
                    hid = None
                    for h in self.map.get('hubs', []):
                        if math.hypot(h['x'] - x, h['y'] - y) < 20:
                            hid = h['id']
                            break
                    if hid:
                        self.spawn_click.append(hid)
                        if len(self.spawn_click) == 2:
                            self.spawn_car(self.spawn_click[0], self.spawn_click[1])
                            self.spawn_click = []

            for h in self.map.get('hubs', []):
                rate = h.get('rate', 1) / 60.0
                if random.random() < rate * dt:
                    dst = random.choice([x for x in self.map.get('hubs', []) if x['id'] != h['id']])
                    self.spawn_car(h['id'], dst['id'])

            self.update(dt)
            self.draw()
        pygame.quit()


# ------------------------------------------------------------
def main():
    if len(sys.argv) > 1:
        mapfile = sys.argv[1]
    else:
        mapfile = os.path.join(os.path.dirname(__file__), '2.json')
    Simulator(mapfile).run()


if __name__ == '__main__':
    main()
