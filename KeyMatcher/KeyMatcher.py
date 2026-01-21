from __future__ import absolute_import, print_function, unicode_literals
import Live
from ableton.v2.control_surface import ControlSurface
from functools import partial
from collections import defaultdict
from ableton.v2.base import liveobj_valid, liveobj_changed
import re

_TROUBLESHOOTING = None
LIVEAPP = Live.Application.get_application()
#region Key Matching
MODE_OFFSETS = {
    'ionian': 0, 'major': 0, 'maj': 0, '': 0,
    'dorian': 2,
    'phrygian': 4,
    'lydian': 5,
    'mixolydian': 7,
    'aeolian': 9, 'minor': 9, 'min': 9, 'm': 9,
    'locrian': 11
}

NOTE_TO_SEMITONE = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4,
    'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8,
    'A': 9, 'A#': 10, 'Bb': 10, 'B': 11, 'Cb': 11, 'B#': 0
}

NOTE_REGEX = re.compile(
    r'(?:(?<=^)|(?<=[\s_\-\(\[]))([A-G][b#]?)\s*(ionian|major|maj|dorian|phrygian|lydian|mixolydian|aeolian|minor|min|m|locrian)?(?:(?=$)|(?=[\s_\.\-\)\]]))',
    re.IGNORECASE
)

def get_transposition(key_name, song):
    project_root = song.root_note % 12
    project_mode = song.scale_name.lower()
    target_offset = MODE_OFFSETS.get(project_mode, 0)
    target_tonal_center = (project_root - target_offset) % 12
    match = NOTE_REGEX.search(key_name)
    if not match:
        return 0
    base_key = match.group(1).capitalize()
    mode_name = match.group(2).lower() if match.group(2) else ''
    clip_root = NOTE_TO_SEMITONE.get(base_key, 0)
    clip_offset = MODE_OFFSETS.get(mode_name, 0)
    clip_tonal_center = (clip_root - clip_offset) % 12
    diff = (target_tonal_center - clip_tonal_center) % 12
    if diff > 6:
        diff -= 12

    return diff

def process_clip(clip, song):
    if clip.is_audio_clip:
        clip_name = clip.file_path # clip.name
        semitones_to_transpose = get_transposition(clip_name, song)
        clip.pitch_coarse = max(-48, min(semitones_to_transpose, 48))
#endregion
class AutoClip(ControlSurface):
    #region Init
    def __init__(self, c_instance):
        global _TROUBLESHOOTING
        _TROUBLESHOOTING = self
        super().__init__(c_instance)
        self.state = self.song.view.draw_mode
        self.changed_main = False
        self.changed_focus = False
        self.clip_snapshot = self.get_clip_snapshot()
        self.add_listeners()
    #endregion
    #region Setup Listeners
    def add_listeners(self):
        self.song.view.add_draw_mode_listener(self.on_change_state)
        LIVEAPP.view.add_view_focus_changed_listener(self.on_change_focus)
        LIVEAPP.view.add_focused_document_view_listener(self.on_change_main)
    def remove_listeners(self):
        self.song.view.remove_draw_mode_listener(self.on_change_state)
        LIVEAPP.view.remove_view_focus_changed_listener(self.on_change_focus)
        LIVEAPP.view.remove_focused_document_view_listener(self.on_change_main)
    #endregion
    #region Trigger Listener Functions
    def on_change_state(self):
        self.state = self.song.view.draw_mode
        self.clip_snapshot.clear()
        self.clip_snapshot = self.get_clip_snapshot()
        #self.show_message(f"Snapshot Reset")

    def on_change_focus(self):
        self.changed_focus = True
        if self.changed_main:
            self.changed_main = False
            if self.state:
                self.clip_snapshot.clear()
                self.clip_snapshot = self.get_clip_snapshot()
                #self.show_message(f"Snapshot Reset")

    def on_change_main(self):
        self.schedule_message(0, self.on_change_main_deferred)
    def on_change_main_deferred(self):
        self.changed_main = True
        if self.changed_focus:
            self.changed_focus = False
            if self.state:
                if self.song.view.detail_clip not in self.clip_snapshot: # Optimization: Compare current clip before comparing all song clips
                    self.batch_process_clip()
    #endregion
    #region Batch Snapshot & Processing
    def get_clip_snapshot(self):
        all_clips = []
        song = self.song
        for track in song.tracks:
            for clip_slot in track.clip_slots:
                if liveobj_valid(clip_slot) and clip_slot.has_clip:
                    all_clips.append(clip_slot.clip)
            for clip_arr in track.arrangement_clips:
                if liveobj_valid(clip_arr):
                    all_clips.append(clip_arr)
                
        return all_clips

    def batch_process_clip(self):
        song = self.song
        message = []
        for track in song.tracks:
            for clip_slot in track.clip_slots:
                if liveobj_valid(clip_slot) and clip_slot.has_clip:
                    if clip_slot.clip not in self.clip_snapshot:
                        process_clip(clip_slot.clip,song)
                        message.append(clip_slot.clip.name)
            for clip_arr in track.arrangement_clips:
                if liveobj_valid(clip_arr):
                    if clip_arr not in self.clip_snapshot:
                        process_clip(clip_arr,song)
                        message.append(clip_arr.name)
        if message: 
            self.show_message("Key Matched for "+ (str(message)))
            self.clip_snapshot.clear()
    #endregion
    #region Disconnect
    def disconnect(self):
        self.remove_listeners()
        super().disconnect()
    #endregion