#!/usr/bin/env python3
# editor.py - Simple Tkinter Map Editor for Traffic Simulator (2D simple)
# Run: python editor.py

import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox, ttk
import json

WIDTH, HEIGHT = 1000, 700
SYMBOL_TYPES = ['slow', 'no_entry']

class Editor:
    def __init__(self, master):
        self.master = master
        master.title('Traffic Map Editor (Simple 2D)')
        self.canvas = tk.Canvas(master, width=WIDTH, height=HEIGHT, bg='white')
        self.canvas.pack(side=tk.LEFT)

        toolbar = tk.Frame(master)
        toolbar.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Button(toolbar, text='Big Road (Dual)', command=self.set_big).pack(fill=tk.X, pady=2)
        tk.Button(toolbar, text='Small Road (One-way)', command=self.set_small).pack(fill=tk.X, pady=2)
        tk.Button(toolbar, text='Add Hub', command=self.add_hub_mode).pack(fill=tk.X, pady=2)
        tk.Button(toolbar, text='Add Light', command=self.add_light_mode).pack(fill=tk.X, pady=2)
        tk.Button(toolbar, text='Add Symbol', command=self.add_symbol_mode).pack(fill=tk.X, pady=2)
        tk.Button(toolbar, text='Select/Move', command=self.set_select).pack(fill=tk.X, pady=2)
        tk.Button(toolbar, text='Save Map', command=self.save_map).pack(fill=tk.X, pady=6)
        tk.Button(toolbar, text='Load Map', command=self.load_map).pack(fill=tk.X, pady=2)

        tk.Label(toolbar, text='Symbol Type:').pack(pady=(10,0))
        self.symbol_type_var = tk.StringVar(value=SYMBOL_TYPES[0])
        ttk.Combobox(toolbar, textvariable=self.symbol_type_var, values=SYMBOL_TYPES).pack(fill=tk.X, padx=4, pady=2)

        self.roads = []
        self.hubs = []
        self.lights = []
        self.symbols = []
        self.id_counter = 1

        self.mode = 'select'
        self.start = None
        self.current_rect = None
        self.selected_item = None

        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)

    def new_id(self):
        i = self.id_counter
        self.id_counter += 1
        return i

    def set_big(self): self.mode = 'big_road'
    def set_small(self): self.mode = 'small_road'
    def add_hub_mode(self): self.mode = 'hub'
    def add_light_mode(self): self.mode = 'light'
    def add_symbol_mode(self): self.mode = 'symbol'
    def set_select(self): self.mode = 'select'

    def on_press(self, event):
        x, y = event.x, event.y
        if self.mode in ('big_road', 'small_road'):
            self.start = (x, y)
            self.current_rect = self.canvas.create_rectangle(x, y, x, y, fill='black', outline='black')
        elif self.mode == 'hub':
            name = simpledialog.askstring('Hub name', 'Enter hub name:', parent=self.master)
            if not name:
                return
            rate = simpledialog.askinteger('Spawn rate', 'Cars per minute:', parent=self.master, minvalue=0, initialvalue=3)
            hid = self.new_id()
            r = 14
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill='gold', outline='black', width=2, tags=(f'hub{hid}',))
            self.canvas.create_text(x, y, text=name, tags=(f'hub_label{hid}',))
            self.hubs.append({'id': hid, 'x': x, 'y': y, 'name': name, 'rate': rate})
        elif self.mode == 'light':
            lid = self.new_id()
            cycle = simpledialog.askinteger('Cycle secs', 'Green/Red cycle seconds (green first):', parent=self.master, minvalue=1,initialvalue=6)
            self.canvas.create_rectangle(x - 6, y - 6, x + 6, y + 6, fill='red', tags=(f'light{lid}',))
            self.lights.append({'id': lid, 'x': x, 'y': y, 'green': cycle, 'red': cycle, 'offset': 0})
        elif self.mode == 'symbol':
            sid = self.new_id()
            stype = self.symbol_type_var.get()
            if stype == 'slow':
                self.canvas.create_rectangle(x - 10, y - 6, x + 10, y + 6, fill='gray', tags=(f'symbol{sid}',))
            else:
                self.canvas.create_polygon(x, y - 10, x - 8, y + 6, x + 8, y + 6, fill='sandybrown', tags=(f'symbol{sid}',))
            self.symbols.append({'id': sid, 'x': x, 'y': y, 'type': stype})
        elif self.mode == 'select':
            item = self.canvas.find_closest(x, y)
            if item:
                self.selected_item = item[0]
                self.sel_start = (x, y)

    def on_drag(self, event):
        x, y = event.x, event.y
        if self.mode in ('big_road', 'small_road') and self.current_rect:
            x0, y0 = self.start
            self.canvas.coords(self.current_rect, x0, y0, x, y)
        elif self.mode == 'select' and self.selected_item:
            dx = x - self.sel_start[0]
            dy = y - self.sel_start[1]
            self.canvas.move(self.selected_item, dx, dy)
            self.sel_start = (x, y)

    def on_release(self, event):
        if self.mode in ('big_road', 'small_road') and self.current_rect:
            x0, y0 = self.start
            x1, y1 = event.x, event.y
            x, y = min(x0, x1), min(y0, y1)
            w, h = abs(x1 - x0), abs(y1 - y0)
            if w < 10 and h < 10:
                self.canvas.delete(self.current_rect)
            else:
                typ = 'big' if self.mode == 'big_road' else 'small'
                rid = self.new_id()
                self.canvas.itemconfig(self.current_rect, tags=(f'road{rid}',))
                self.roads.append({'id': rid, 'x': x, 'y': y, 'w': w, 'h': h, 'type': typ})
            self.current_rect = None
            self.start = None
        elif self.mode == 'select':
            self.selected_item = None

    def save_map(self):
        filepath = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON','*.json')])
        if not filepath:
            return
        data = {'roads': self.roads, 'hubs': self.hubs, 'lights': self.lights, 'symbols': self.symbols}
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        messagebox.showinfo('Saved', f'Map saved to {filepath}')

    def load_map(self):
        filepath = filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if not filepath:
            return
        with open(filepath) as f:
            data = json.load(f)
        self.roads = data.get('roads', [])
        self.hubs = data.get('hubs', [])
        self.lights = data.get('lights', [])
        self.symbols = data.get('symbols', [])
        self.canvas.delete('all')
        for r in self.roads:
            self.canvas.create_rectangle(r['x'], r['y'], r['x']+r['w'], r['y']+r['h'], fill='black', tags=(f'road{r["id"]}',))
        for h in self.hubs:
            r = 14
            self.canvas.create_oval(h['x']-r, h['y']-r, h['x']+r, h['y']+r, fill='gold', outline='black', width=2, tags=(f'hub{h["id"]}',))
            self.canvas.create_text(h['x'], h['y'], text=h.get('name',''))
        for l in self.lights:
            self.canvas.create_rectangle(l['x']-6, l['y']-6, l['x']+6, l['y']+6, fill='red')
        for s in self.symbols:
            if s.get('type') == 'slow':
                self.canvas.create_rectangle(s['x']-10, s['y']-6, s['x']+10, s['y']+6, fill='gray')
            else:
                x, y = s['x'], s['y']
                self.canvas.create_polygon(x, y-10, x-8, y+6, x+8, y+6, fill='sandybrown')
        messagebox.showinfo('Loaded', 'Map loaded')


if __name__ == '__main__':
    root = tk.Tk()
    app = Editor(root)
    root.mainloop()
