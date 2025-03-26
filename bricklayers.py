#!/usr/bin/env python3
__version__ = "v0.2.1-10-g6409588"  # Updated by GitHub Actions

# Brick Layers by Geek Detour
# Interlocking Layers Post-Processing Script for PrusaSlicer, OrcaSlicer, and BambuStudio
#
# Copyright (C) 2025 Everson Siqueira, Geek Detour
# 
# You can support my work on Patreon:
#  - https://www.patreon.com/c/GeekDetour
#    I really appreciate your help!
#
#
#
# IMPORTANT SETTINGS on your Slicer:
#
#  - "Inner/Outer" is the BEST setting for Walls Printing Order. 
#    "Outer/Inner" works 'most of the time', but there could be glitches.
#    "Inner/Outer/Inner" is NOT recommended.
#       But don't worry: use Inner/Outer and Brick Layers basically delivers
#       what you expected from Inner/Outer/Inner.
#
#  - PrusaSlicer: "Arachne" and "Classic" engines work equally well :)
#                  If you really need Arachne, PrusaSlicer is the way to go.
#
#  - OrcaSlicer:  "Classic" engine works very well :)
#                 "Arachne" doesn't always generate consistent loop order for inner-walls :(
#                  https://github.com/SoftFever/OrcaSlicer/issues/884
#                  I tried circumventing the problem, but it was increasing the complexity a lot!
#
#  - BambuStudio: "Classic" engine works very well :)
#                 "Arachne" has the same unpredictable loop order variations as OrcaSlicer
#                  'Cancel Object' still needs specific implementation for Bambu Printers
#
#
# About Brick Layers:
#  - https://youtu.be/9IdNA_hWiyE 
#   "Brick Layers: Stronger 3D Prints TODAY - instead of 2040"
#  - https://www.patreon.com/posts/115566868 
#   "Brick Layers": Slicers can have it Today (instead of 2040)"
#  - https://youtu.be/qqJOa46OTTs (* about this script *)
#   "Brick Layers for everybody: Prusa Slicer, Orca Slicer and Bambu Studio"
#
#    This Script transforms the arrangement of the perimeter beads on a GCode file,
#    converting the Rectangular arrangement into a Hexagonal arrangement.
#
#    The Hexagonal 3D Printing pattern is Public Domain, since 2016.
#    Batchelder: US005653925A (1995), EP0852760B1 (1996)
#
#
# Special thanks to my fellow YouTubers:
#
#  - Stefan Hermann,  "CNC Kitchen"
#  - Dr. Igor Gaspar, "My Tech Fun"
#  - Roman Tenger,    "TenTech"
#
#
#
# This program is free software: you can redistribute it and/or modify
#
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Repository:
#  - https://github.com/GeekDetour/BrickLayers


import traceback # On the very top

# LOGGING:
import logging
logger = logging.getLogger(__name__)


from typing import Dict
class ObjectEntry:
    """Stores the Name of the objects being printed, as a lightweight single object reference"""
    _registry: Dict[str, "ObjectEntry"] = {}

    def __init__(self, name: str):
        self.name = name  # Store the unique name

    def __repr__(self):
        return f"ObjectEntry({self.name})"
    
    @classmethod
    def entry_from_name(cls, name: str) -> "ObjectEntry":
        """Retrieves an ObjectEntry from the registry or creates a new one if not present."""
        if name not in cls._registry:
            cls._registry[name] = cls(name)
        return cls._registry[name]

    @classmethod
    def clear_registry(cls):
        """Clears all stored ObjectEntry instances from the registry."""
        cls._registry.clear()


import math
from typing import NamedTuple
class Point(NamedTuple):
    """Point For all calculations"""
    x: float
    y: float

    @staticmethod
    def distance_between_points(s_from, s_to):
        """Calculates Euclidean distance between two states, using .x and .y properties."""
        dx = s_to.x - s_from.x
        dy = s_to.y - s_from.y
        return math.sqrt(dx * dx + dy * dy)

    @staticmethod
    def point_along_line_forward(p_from, p_to, desired_distance):
        """Find a point `desired_distance` forward from p_from toward p_to.

        p_from and p_to must have .x and .y attributes (NamedTuple, State, etc.).
        Returns a new plain Point.
        """

        dx = p_to.x - p_from.x
        dy = p_to.y - p_from.y

        full_length = math.sqrt(dx * dx + dy * dy)

        if full_length <= 0.0:
            # No movement — just return p_from as a point
            return Point(p_from.x, p_from.y)

        # Fraction of the full line we want to move forward
        fraction = desired_distance / full_length

        # New point forward along the line
        new_x = p_from.x + dx * fraction
        new_y = p_from.y + dy * fraction

        return Point(new_x, new_y)

    @staticmethod
    def point_along_line_backward(from_pos, to_pos, distance):
        # Same as forward, but the "from" and "to" are swapped.
        direction = ((from_pos.x - to_pos.x), (from_pos.y - to_pos.y))
        length = math.sqrt(direction[0]**2 + direction[1]**2)

        if length < 1e-6:
            return to_pos  # No movement possible (tiny segment)

        scale = distance / length
        new_x = to_pos.x + direction[0] * scale
        new_y = to_pos.y + direction[1] * scale
        return Point(new_x, new_y)


class GCodeState(NamedTuple):
    """Printing State"""
    x: float
    y: float
    z: float
    e: float
    f: float
    retracted: float
    width: float
    absolute_positioning: bool
    relative_extrusion: bool
    is_moving: bool
    is_extruding: bool
    is_retracting: bool
    just_started_extruding: bool
    just_stopped_extruding: bool


class GCodeFeatureState(NamedTuple):
    """Feature State"""
    layer: int
    z: float
    height: float
    layer_change: bool
    current_object: ObjectEntry
    current_type: str
    last_type: str
    overhang_perimeter: bool
    internal_perimeter: bool
    external_perimeter: bool
    justgotinside_internal_perimeter: bool
    justleft_internal_perimeter: bool
    justgotinside_external_perimeter: bool
    just_changed_type: bool
    wiping: bool
    wipe_willfinish: bool
    wipe_justfinished: bool
    capture_height: bool


class GCodeStateBBox:
    """Bounding-Box calculator to detect non-concentric loops.
    This implementation is highly efficient, using simple vertical and horizontal calculations 
    instead of computing the Euclidean distance from centers (which would require a square root operation)."""

    __slots__ = ('min_x', 'max_x', 'min_y', 'max_y')  # Minimalist and memory-efficient!

    def __init__(self):
        self.min_x = float('inf')
        self.max_x = float('-inf')
        self.min_y = float('inf')
        self.max_y = float('-inf')

    def compute(self, state: GCodeState):
        """Feeds a point into the bounding box, updating its min/max values."""
        x = state.x
        y = state.y
        if self.min_x == float('inf'):  # First point ever
            self.min_x = x - 0.1  # Expand opposite sides to ensure nonzero size
            self.max_x = x + 0.1
            self.min_y = y - 0.1
            self.max_y = y + 0.1
        else:
            self.min_x = min(self.min_x, x)
            self.max_x = max(self.max_x, x)
            self.min_y = min(self.min_y, y)
            self.max_y = max(self.max_y, y)

    def contains(self, other) -> bool:
        """Checks if this bounding box fully contains another bounding box."""
        return (
            self.min_x <= other.min_x and  # This box starts before the other on X-axis
            self.max_x >= other.max_x and  # This box ends after the other on X-axis
            self.min_y <= other.min_y and  # This box starts before the other on Y-axis
            self.max_y >= other.max_y      # This box ends after the other on Y-axis
        )

    def get_center(self):
        """Returns the center (midpoint) of the bounding box."""
        return ((self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2)

    def get_size(self):
        """Returns the width and height of the bounding box."""
        return (self.max_x - self.min_x, self.max_y - self.min_y)

    def copy_from(self, other: "GCodeStateBBox"):
        """Copies bounding box values from another BBox instance."""
        self.min_x = other.min_x
        self.max_x = other.max_x
        self.min_y = other.min_y
        self.max_y = other.max_y

    def reset(self):
        """Resets the bounding box to its initial infinite state."""
        self.min_x = float('inf')
        self.max_x = float('-inf')
        self.min_y = float('inf')
        self.max_y = float('-inf')

    def __repr__(self):
        """Returns a dictionary representation of the bounding box for easy debugging."""
        center_x, center_y = self.get_center()
        width, height = self.get_size()
        return f"GCodeStateBBox(center_x={center_x:.3f}, center_y={center_y:.3f}, width={width:.3f}, height={height:.3f})"


from typing import Optional
import re
class GCodeLine:
    """Encapusates one GCode line, plus print states and a reference to which Printing Object the line belongs
    It can contain a calculated `looporder` and concentric loops have the same 'contentric_grop' number
    """
    __slots__ = ('gcode', 'previous', 'current', 'object', 'looporder', 'concentric_group')

    regex_x = re.compile(r'X[-+]?[0-9]*\.?[0-9]+')
    regex_y = re.compile(r'Y[-+]?[0-9]*\.?[0-9]+')

    def __init__(self, gcode: str, previous: Optional[GCodeState] = None,
                 current: Optional[GCodeState] = None, object_ref: Optional[ObjectEntry] = None, looporder: Optional[int] = None, concentric_group: Optional[int] = None):
        self.gcode = gcode
        self.previous = previous
        self.current = current
        self.object = object_ref  # Stores a reference (pointer) to ObjectEntry
        self.looporder = looporder
        self.concentric_group = concentric_group

    def __repr__(self):
        return (f"GCodeLine(command='{self.gcode}', "
                f"previous={self.previous}, current={self.current}, object={self.object}, looporder={self.looporder}, concentric_group={self.concentric_group})")
    
    def to_gcode(self) -> str:
        return self.gcode

    def update_xy(self, new_x, new_y):
        gcode = self.gcode
        gcode = GCodeLine.regex_x.sub(f'X{new_x}', gcode)
        gcode = GCodeLine.regex_y.sub(f'Y{new_y}', gcode)
        self.gcode = gcode

    @staticmethod
    def from_gcode(gcode: str, previous: Optional[GCodeState] = None, current: Optional[GCodeState] = None, object_ref: Optional[ObjectEntry] = None) -> "GCodeLine":
        """Creates a GCodeLine instance from a raw G-code line without modifications. That should inclute a \\n at the very end"""
        return GCodeLine(gcode, previous, current, object_ref)




class GCodeFeature:
    """
    GCodeFeature: A state tracker for parsing G-code and identifying print features.

    This class analyzes G-code lines to detect and classify different print features, such as 
    internal/external perimeters, overhangs, layer changes, and wiping commands. It maintains 
    a compact internal state using `__slots__` for efficient memory usage.

    ### Key Responsibilities:
    - Tracks **layer height (Z), layer changes, and print feature types**.
    - Identifies whether a segment is an **internal or external perimeter**, ensuring independence 
    from slicer-specific terminology (e.g., PrusaSlicer vs. OrcaSlicer).
    - Detects **overhang walls**, which are currently exclusive to OrcaSlicer.
    - Recognizes **wipe movements** (`;WIPE_START`, `;WIPE_END`) and manages their transitions.
    - Monitors **object changes** when switching between printed objects.
    - Efficiently captures **layer height information** while avoiding redundant updates.

    ### Parsing Behavior:
    - G-code comments like `;TYPE:xxx` define different print features.
    - Special markers such as `;LAYER_CHANGE` and `;Z:` update layer state.
    - Wiping operations are handled by tracking their start and end points.
    - When the print ends (`;END of PRINT`), the state resets accordingly.
    """
    __slots__ = ('layer', 'z', 'height', 'layer_change', 'current_object', 'current_type', 'last_type', 'overhang_perimeter', 'internal_perimeter', 'external_perimeter', 'justgotinside_internal_perimeter', 'justleft_internal_perimeter', 'justgotinside_external_perimeter', 'just_changed_type', 'wiping', 'wipe_willfinish', 'wipe_justfinished', 'capture_height')
    
    DEF_TYPES = (";TYPE:", "; FEATURE: ") # tupple, for line.startswith
    DEF_INNERPERIMETERS = {"Perimeter", "Inner wall"} # set, for fast equality check
    DEF_OUTERPERIMETERS = {"External perimeter", "Outer wall"}
    DEF_OVERHANGPERIMETERS = {"Overhang wall"}
    DEF_WIPESTARTS   = {";WIPE_START", "; WIPE_START"}
    DEF_WIPEENDS     = {";WIPE_END",   "; WIPE_END"}
    DEF_LAYERCHANGES = {";LAYER_CHANGE", "; CHANGE_LAYER"}
    DEF_LAYER_HEIGHTS = (";HEIGHT:", "; LAYER_HEIGHT: ") # tupple, for line.startswith
    DEF_LAYER_ZS      = (";Z:", "; Z_HEIGHT: ")          # tupple, for line.startswith

    DEF_START_PRINTING_OBJECTS = ("; printing object ", "; start printing object, ")
    DEF_STOP_PRINTING_OBJECTS  = ("; stop printing object ", "; stop printing object, ")

    SANE_INNERPERIMETER    = "internal_perimeter"
    SANE_OUTERPERIMETER    = "external_perimeter"
    SANE_OVERHANGPERIMETER = "overhang_perimeter"

    # Must be detected and set once:
    internal_perimeter_type = None
    external_perimeter_type = None
    const_wipe_start = None
    const_wipe_end   = None
    const_printingobject_start  = None
    const_printingobject_stop   = None
    const_layer_change   = None
    const_layer_height   = None
    const_layer_z        = None


    def __init__(self):
        self.layer = 0
        self.z = 0.0
        self.height = 0.0
        self.layer_change = False
        self.current_object: Optional[ObjectEntry] = None
        self.current_type = ""
        self.last_type = ""
        self.overhang_perimeter = False
        self.internal_perimeter = False
        self.external_perimeter = False
        self.justgotinside_internal_perimeter = False
        self.justleft_internal_perimeter = False
        self.justgotinside_external_perimeter = False
        self.just_changed_type = False
        self.wiping = False
        self.wipe_willfinish = False
        self.wipe_justfinished = True
        self.capture_height = True


    def parse_gcode_line(self, line):
        """
        Captures a Feature definition
        Ex: Perimeter, External perimeter, Internal infill, etc...
        Anything that begins the line as: ;TYPE:xxx        
        """
        strippedline = line.strip()

        # Change Detection:
        old_internal_perimeter = self.internal_perimeter
        # Reseting
        self.just_changed_type = False
        self.justgotinside_internal_perimeter = False
        self.justgotinside_external_perimeter = False
        self.justleft_internal_perimeter = False
        self.wipe_justfinished = False
        self.layer_change = False

        if self.wipe_willfinish:
            self.wiping = False
            self.wipe_justfinished = True
            self.wipe_willfinish = False


        # This fuction (so far) only checks things that start with ";SOMETHING"
        if line and line[0] != ";":
             return self # no point in proceed checking further

        if line.startswith(self.DEF_TYPES):
            old_type = self.current_type
            self.just_changed_type = True # TODO: revise

            #new_type = line.split(";TYPE:")[1].strip()
            for prefix in self.DEF_TYPES:
                if line.startswith(prefix):
                    new_type = line[len(prefix):].strip()
                    break

            if new_type in self.DEF_INNERPERIMETERS:
                if self.internal_perimeter_type is None:
                    type(self).internal_perimeter_type = line
                self.current_type = self.SANE_INNERPERIMETER #sanitizing to be independent of PrusaSlicer, OrcaSlicer or BambuStudio
                if not self.internal_perimeter:
                    self.justgotinside_internal_perimeter = True
                self.internal_perimeter = True
                self.external_perimeter = False
                self.overhang_perimeter = False

            elif new_type in self.DEF_OUTERPERIMETERS:
                if self.external_perimeter_type is None:
                    type(self).external_perimeter_type = line
                self.current_type = self.SANE_OUTERPERIMETER #sanitizing to be independent of PrusaSlicer, OrcaSlicer or BambuStudio
                if not self.external_perimeter:
                    self.justgotinside_external_perimeter = True
                self.external_perimeter = True
                self.internal_perimeter = False
                self.overhang_perimeter = False

            elif new_type in self.DEF_OVERHANGPERIMETERS: # OrcaSlicer only, so far...
                self.current_type = self.SANE_OVERHANGPERIMETER
                self.overhang_perimeter = True

            else:
                self.internal_perimeter = False
                self.external_perimeter = False
                self.overhang_perimeter = False
                self.current_type = new_type

            if old_internal_perimeter and not self.internal_perimeter:
                self.justleft_internal_perimeter = True

        elif strippedline in self.DEF_WIPESTARTS:
            self.wiping = True
            if self.const_wipe_start is None:
                for prefix in self.DEF_WIPESTARTS:
                    if strippedline.startswith(prefix):
                        type(self).const_wipe_start = prefix + "\n"
                        break     

        elif strippedline in self.DEF_WIPEENDS:
            self.wipe_willfinish = True
            if self.const_wipe_end is None:
                for prefix in self.DEF_WIPEENDS:
                    if strippedline.startswith(prefix):
                        type(self).const_wipe_end = prefix + "\n"
                        break

        elif strippedline.startswith(self.DEF_START_PRINTING_OBJECTS):
            for prefix in self.DEF_START_PRINTING_OBJECTS:
                if strippedline.startswith(prefix):
                    object_name = strippedline[len(prefix):]
                    break
            # Captures the right 'start object' flavor used in the file being parsed
            if self.const_printingobject_start is None:
                type(self).const_printingobject_start = prefix
            # Assigns a pointer to the lastly object being printed:
            self.current_object = ObjectEntry.entry_from_name(object_name)

        elif self.const_printingobject_stop is None and strippedline.startswith(self.DEF_STOP_PRINTING_OBJECTS):
            # Just captures the right 'stop object' flavor used in the file being parsed
            for prefix in self.DEF_STOP_PRINTING_OBJECTS:
                if strippedline.startswith(prefix):
                    break
            type(self).const_printingobject_stop = prefix

        elif strippedline in self.DEF_LAYERCHANGES:
            if self.const_layer_change is None:
                for prefix in self.DEF_LAYERCHANGES:
                    if strippedline.startswith(prefix):
                        type(self).const_layer_change = line
                        break
            self.layer_change = True
            self.internal_perimeter = False # THIS IS TECHNICALLY WRONG! Sometimes OrcaSlicer just continues the previous Type on a new layer!
            self.external_perimeter = False # THIS IS TECHNICALLY WRONG! Sometimes OrcaSlicer just continues the previous Type on a new layer!
            self.layer += 1
            self.capture_height = True # I need to capture only once per layer.


        #elif line.startswith(";Z:"):
        elif strippedline.startswith(self.DEF_LAYER_ZS):
            for prefix in self.DEF_LAYER_ZS:
                if strippedline.startswith(prefix):
                    self.z = float(strippedline[len(prefix):])
                    break
            if self.const_layer_z is None:
                type(self).const_layer_z = prefix

        #elif line.startswith(";HEIGHT:"):
        elif strippedline.startswith(self.DEF_LAYER_HEIGHTS):
            if self.capture_height:
                for prefix in self.DEF_LAYER_HEIGHTS:
                    if strippedline.startswith(prefix):
                        self.height = float(strippedline[len(prefix):])
                        self.capture_height = False
                        break
                if self.const_layer_height is None:
                    type(self).const_layer_height = prefix

        if not self.just_changed_type:
            self.last_type = self.current_type # Allows for feature change.

        return self


    def get_state(self):
        """Returns a dictionary representation of the feature state."""
        return GCodeFeatureState(
            layer=self.layer,
            z=self.z,
            height=self.height,
            layer_change=self.layer_change,
            current_object=self.current_object,
            current_type=self.current_type,
            last_type=self.last_type,
            overhang_perimeter=self.overhang_perimeter,
            internal_perimeter=self.internal_perimeter,
            external_perimeter=self.external_perimeter,
            justgotinside_internal_perimeter=self.justgotinside_internal_perimeter,
            justleft_internal_perimeter=self.justleft_internal_perimeter,
            justgotinside_external_perimeter=self.justgotinside_external_perimeter,
            just_changed_type=self.just_changed_type,
            wiping=self.wiping,
            wipe_willfinish=self.wipe_willfinish,
            wipe_justfinished=self.wipe_justfinished,
            capture_height=self.capture_height
        )
    

class GCodeSimulator:
    """
    GCodeSimulator: A lightweight G-code state tracker.

    This class interprets individual G-code lines, updating a simulated state that reflects 
    the machine's movement, extrusion, and positioning. It calculates state changes when parsing 
    gcode lines, updating key parameters such as X, Y, Z coordinates, extrusion (E), and feed rate (F).

    ### Features:
    - Supports both **absolute (G90)** and **relative (G91)** positioning.
    - Tracks **extrusion mode** (absolute M82 / relative M83).
    - Identifies **movement commands (G0, G1, G2, G3)**, updating values accordingly.
    - Detects **maximum travel and retraction speeds** encountered in the parsed G-code.
    - Makes it easy to know track changes in extrusion sequences (just_stopped_extruding)
    - Also accounts for the WIDTH (used just on the preview of slicers: `;WIDTH:x.xx`)
    - Provides a snapshot of the current state via `get_state()`.

    It uses `__slots__` to minimize memory overhead, and make it efficient for parsing large G-code files.
    """

    __slots__ = ('x', 'y', 'z', 'e', 'f', 'retracted', 'width', 'absolute_positioning', 'relative_extrusion', 'is_moving', 'is_extruding', 'is_retracting', 'just_started_extruding', 'just_stopped_extruding', 'moved_in_xy', 'travel_speed', 'wipe_speed', 'retraction_speed', 'detraction_speed', 'retraction_length')

    DEF_WIDTHS = (";WIDTH:", "; LINE_WIDTH: ")    # tupple, for line.startswith

    # Must be detected and set once:
    const_width          = None

    def __init__(self, initial_state=None):
        self.x, self.y, self.z, self.e, self.f, self.retracted, self.width = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        self.absolute_positioning = True  # Default mode is absolute (G90)
        self.relative_extrusion = False  # Default extrusion mode is absolute (M82)
        self.is_moving = False  # Tracks whether movement is happening
        self.is_extruding = False  # Tracks whether extrusion is happening
        self.is_retracting = False  # Tracks whether extrusion is happening
        self.just_started_extruding = False
        self.just_stopped_extruding = False  # Tracks whether a MOVEMENT doesn't extrude, right after another MOVEMENT that was extruding
        self.moved_in_xy = False # Tracks movements that occur in X and Y
        self.travel_speed = 0
        self.wipe_speed = 0
        self.retraction_speed = 0
        self.detraction_speed = 0
        self.retraction_length = 0

        if initial_state:
            self.set_state(initial_state)


    def parse_gcode_line(self, rawline):
        stripline = rawline.strip()
        line = stripline

        if not line:  # Skip empty lines
            return self

        #Reset
        self.just_stopped_extruding = False

        # Remove inline comments
        line = line.partition(';')[0]

        if line:
            parts = line.split()
            command = parts[0]

            if command in ('G0', 'G1', 'G2', 'G3'):

                # Remember old extruding state for transitions
                old_extruding = self.is_extruding

                # Reset line flags
                self.moved_in_xy = False
                self.is_extruding = False
                self.is_retracting = False
                self.just_stopped_extruding = False


                # Movement commands
                abs_pos = self.absolute_positioning
                rel_ext = self.relative_extrusion


                old_x, old_y, old_z, old_e = self.x, self.y, self.z, self.e
                new_x, new_y, new_z = self.x, self.y, self.z
                new_e, new_f = self.e, self.f
                has_x, has_y, has_z, has_e, has_f = False, False, False, False, False

                for arg in parts[1:]:
                    axis = arg[0]
                    # Skip I/J if arcs
                    if axis in ('I', 'J'):
                        continue

                    val = float(arg[1:])
                    if axis == 'X':
                        new_x = val if abs_pos else (self.x + val)
                        has_x = True
                    elif axis == 'Y':
                        new_y = val if abs_pos else (self.y + val)
                        has_y = True
                    elif axis == 'Z':
                        new_z = val if abs_pos else (self.z + val)
                        has_z = True
                    elif axis == 'E':
                        # E can be absolute or relative
                        if rel_ext:
                            new_e = self.e + val
                        else:
                            new_e = val
                        has_e = True
                    elif axis == 'F':
                        new_f = val
                        has_f = True

                # Detect if there is actual X/Y/Z movement
                x_move = (new_x != old_x)
                y_move = (new_y != old_y)
                z_move = (new_z != old_z)
                had_a_movement_change = x_move or y_move or z_move # In this very line

                self.moved_in_xy = (x_move or y_move)

                just_feed_rate = ( has_f and not (has_x or has_y or has_z) )

                if (has_x or has_y or has_z):
                    # Update positions
                    self.x, self.y, self.z = new_x, new_y, new_z
                
                self.e, self.f = new_e, new_f

                extruding = False
                retracting = False
                extruded = new_e - old_e
                if extruded > 0:
                    extruding = True
                    self.is_extruding = True
                elif extruded < 0:
                    retracting = True
                    self.is_retracting = True
        
                self.retracted += extruded
                if self.retracted + 0.0001 > 0:
                    self.retracted = 0.0

                # Detect Maximum Travel Speed:
                if had_a_movement_change and new_e == old_e and self.travel_speed < new_f:
                    self.travel_speed = new_f
                    logger.debug(f"travel_speed: {new_f}, gcode: {line}")

                # Detect Retraction Length:
                if not had_a_movement_change and retracting and  abs(extruded) > self.retraction_length: # and self.retraction_speed < new_f:
                    #self.retraction_speed = new_f 
                    self.retraction_length = abs(extruded)
                    logger.debug(f"retraction_speed: {new_f}, gcode: {line}, retraction_length: {self.retraction_length}, old_e: {old_e}, new_e: {new_e}")

                if had_a_movement_change:
                    self.is_moving = True
                elif extruded != 0 and not had_a_movement_change:
                    self.is_moving = False

                if (not just_feed_rate):

                    # Transitional Marker:
                    self.just_started_extruding = (extruding and not old_extruding and had_a_movement_change)

                    # Transitional Marker:
                    if old_extruding and not self.is_extruding:
                        self.just_stopped_extruding = True

            elif command == 'G90':
                self.absolute_positioning = True

            elif command == 'G91':
                self.absolute_positioning = False

            elif command == 'M82':
                self.relative_extrusion = False

            elif command == 'M83':
                self.relative_extrusion = True

            elif command == 'G92':
                # Set axis positions (e.g. G92 X10 Y20 E0)
                for arg in parts[1:]:
                    axis = arg[0].upper()
                    if axis in "XYZE":
                        val = float(arg[1:])
                        setattr(self, axis.lower(), val)
                if self.e == 0:
                    self.retracted = 0

        elif stripline.startswith(self.DEF_WIDTHS):
            for prefix in self.DEF_WIDTHS:
                if stripline.startswith(prefix):
                    self.width = float(stripline[len(prefix):])
                    break
            if self.const_width is None:
                type(self).const_width = prefix

        return self

    def get_state(self):
        return GCodeState(
            x=self.x,
            y=self.y,
            z=self.z,
            e=self.e,
            f=self.f,
            retracted=self.retracted,
            width=self.width,
            absolute_positioning=self.absolute_positioning,
            relative_extrusion=self.relative_extrusion,
            is_moving=self.is_moving,
            is_extruding=self.is_extruding,
            is_retracting=self.is_retracting,
            just_started_extruding=self.just_started_extruding,
            just_stopped_extruding=self.just_stopped_extruding
        )

    def set_state(self, state: GCodeState):
        if not isinstance(state, GCodeState):
            raise TypeError("Expected a GCodeState instance")
        self.x = state.x
        self.y = state.y
        self.z = state.z
        self.e = state.e
        self.f = state.f
        self.retracted = state.retracted
        self.width = state.width
        self.absolute_positioning = state.absolute_positioning
        self.relative_extrusion = state.relative_extrusion
        self.is_moving = state.is_moving
        self.is_extruding = state.is_extruding
        self.is_retracting= state.is_retracting
        self.is_extruding_and_moving = state.is_extruding_and_moving
        self.just_started_extruding = state.just_started_extruding
        self.just_stopped_extruding = state.just_stopped_extruding

    def reset_state(self):
        self.x, self.y, self.z, self.e, self.f, self.retracted, self.width = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        self.absolute_positioning = True
        self.relative_extrusion = False
        self.is_moving = False
        self.is_extruding = False
        self.is_retracting = False
        self.is_extruding_and_moving = False
        self.just_started_extruding = False
        self.just_stopped_extruding = False
        self.travel_speed = 0   
        self.wipe_speed = 0
        self.retraction_speed = 0
        self.detraction_speed = 0
        self.retraction_length = 0

class LoopIsland:

    __slots__ =  ('loops','start','end','start_state','end_state')
    def __init__(self,start):
        self.loops=[]
        self.start=start
        self.end=start+1
        self.start_state=None
        self.end_state=None
    
    def set_start(self,start_line,state):
        self.start=start_line
        self.start_state=state
    
    def set_end(self,end_line,state):
        self.end=end_line
        self.end_state=state

    def append(self,loop):
        self.loops.append(loop)

    def __len__(self):
        return len(self.loops)

class LoopNode:
    """Temporary structure to track nesting relationships of LOOPS during processing."""
    __slots__ = ('around_hole', 'depth', 'boundingbox', 'order', 'looplines', 'kids')

    concentric = 0  # Centralized variable to be incremented, so every group of tightly nested loops have the same one. No branch should have the same number.

    def __init__(self, order, boundingbox, looplines):
        self.around_hole = False
        self.depth = 0  # Assigned later
        self.boundingbox = boundingbox
        self.order = order  # The index of the original groups list, to be able to elaborate a 'moving' list based on that order.
        self.looplines = looplines  # the ORIGINAL list of lines (It is referenced on other structures)
        self.kids = []
    
    def propagate(self, boolean_list, depth = 0, myconcentric = None):
        if myconcentric is None:
            LoopNode.concentric += 1
            myconcentric = LoopNode.concentric

        self.depth = depth 

        total_kids = len(self.kids)
        if total_kids == 1:
            # use the same concentric as the parent node:
            kid_depth = self.kids[0].propagate(boolean_list, depth + 1, LoopNode.concentric)
        elif total_kids > 1:
            for kid in self.kids: 
                LoopNode.concentric += 1 # Increment the unique counter
                kid_depth = kid.propagate(boolean_list, depth + 1, LoopNode.concentric) # Each branch needs a unique number
        
        if self.around_hole:
            if total_kids == 0:
                # Around a hole, this is the loop closest to the external perimeter:
                self.depth = 0
                depth = 0
            elif kid_depth is not None: #TODO: investigate cases in which a hole would not return depth
                self.depth = kid_depth
                depth = kid_depth

        # Update boolean list based on depth rule
        if (depth + 1) % 2:
            boolean_list[self.order] = True

        # This is the real place these values will change things:
        for line in self.looplines:
            line.looporder = depth  # `looporder`: property of a "GCodeLine" instance
            line.concentric_group = myconcentric  # `concentric_group`: property of "GCodeLine"

        if self.around_hole:
            return depth + 1

    def contains_point(self,point):
        winding=0
        for line in self.looplines:
            edge_start = line.previous
            edge_end = line.current
            side = (edge_end.x-edge_start.x)*(point.y-edge_start.y) - (point.x-edge_start.x)*(edge_end.y-edge_start.y)
            if edge_start.y <= point.y:
                if edge_end.y>point.y:
                    if side<0:
                        winding+=1
            else:
                if edge_end.y<=point.y:
                    if side>0:
                            winding-=1
        edge_start = self.looplines[-1].current
        edge_end = self.looplines[0].previous
        side = (edge_end.x-edge_start.x)*(point.y-edge_start.y) - (point.x-edge_start.x)*(edge_end.y-edge_start.y)
        if edge_start.y <= point.y:
            if edge_end.y>point.y:
                if side<0:
                    winding+=1
        else:
            if edge_end.y<=point.y:
                if side>0:
                    winding-=1
                
        logger.info(f"winding = {winding}")
        return winding!=0

    def __repr__(self):
        keys_to_include = {"gcode"}
        return (f"LoopNode(around_hole={self.around_hole} , order={self.order}, depth={self.depth}, "
                f"kids={self.kids}, "
                f"looplines={len(self.looplines)}" # [line.gcode for line in self.looplines]
                #f"looplines={brick_to_serializable(self.looplines, keys_to_include)}"
                )



def brick_dump(text, obj, keys_to_include=None):
    if not hasattr(brick_dump, "_json"):
        import json
        brick_dump._json = json  # Cache it in a function attribute
    return(f"{text}:\n{brick_dump._json.dumps(brick_to_serializable(obj, keys_to_include), indent=4)}\n\n")

def brick_to_serializable(obj, keys_to_include=None):
    """Recursively converts objects into JSON-serializable structures, including only specified keys.
    Allows json.dumps(obj) on many of the objects of this module, for easier debugging.
    """
    if keys_to_include is None:
        keys_to_include = set()
    # Serializes GCodeLine:
    if isinstance(obj, GCodeLine):
        if len(keys_to_include) == 1:
            first_key = next(iter(keys_to_include))  # Get the single key correctly
            return getattr(obj, first_key)  # Return its value
        else:
            return {key: getattr(obj, key) for key in obj.__slots__ if key in keys_to_include}
    # Serializes LoopNode:
    elif isinstance(obj, LoopNode):
        return {
            "around_hole": obj.around_hole,
            "order": obj.order,
            "depth": obj.depth,
            "kids": [brick_to_serializable(kid, keys_to_include) for kid in obj.kids],  # Recursively serialize kids
            "looplines": len(obj.looplines)  # Serialize looplines
        }
    # Handle lists, tuples, and sets (process each item)
    elif isinstance(obj, (list, tuple, set)):
        return [brick_to_serializable(item, keys_to_include) for item in obj]
    # Handle dictionaries (convert values recursively)
    elif isinstance(obj, dict):
        return {key: brick_to_serializable(value, keys_to_include) for key, value in obj.items()}
    # Base case: return the object if it’s already serializable
    return obj



from typing import Callable, Optional
class BrickLayersProcessor:
    """
    BrickLayersProcessor: G-Code Post-Processor for Brick Layering.

    This class modifies G-code to implement the Brick Layers technique, improving part 
    strength by redistributing inner perimeters across multiple layers. It processes 
    G-code line by line, adjusting extrusion values and modifying movement paths based 
    on detected features and geometric constraints.

    ### Features:
    - **Layer-Based Processing:**
    - Starts processing at a configurable layer (`start_at_layer`).
    - Allows exclusion of specific layers (`layers_to_ignore`).
    - Detects and handles layer changes (`;LAYER_CHANGE`).

    - **Extrusion Adjustments:**
    - Applies a global extrusion multiplier (`extrusion_global_multiplier`).
    - Supports absolute and relative extrusion modes.

    - **Internal Perimeter Redistribution:**
    - Identifies **non-concentric inner perimeters** (orphaned loops).
    - Groups inner loops into concentric and non-concentric sets.
    - Moves selected loops to a higher layer for improved adhesion.

    - **Retraction and Travel Optimizations:**
    - Detects **maximum travel and retraction speeds**.
    - Inserts retractions and travel moves when necessary
    - Implements it's own 'Wiping'

    - **G-Code Feature Detection:**
    - Identifies feature types (`;TYPE:`) such as internal/external perimeters and infill.
    - Normalizes slicer-specific naming (e.g., PrusaSlicer vs. OrcaSlicer).
    - Captures object changes for Cancel Objects (`; printing object`).

    - **Progress Reporting:**
    - Supports an optional **progress callback** (`progress_callback`).
    - Provides updates on bytes processed, layers, and line counts.

    Optimized for efficiency using **line-by-line processing**, for processing Big Gcode files
    """
    def __init__(self, extrusion_global_multiplier: float = 1.05, start_at_layer: int = 3, layers_to_ignore = None, verbosity: int = 0, progress_callback: Optional[Callable[[dict], None]] = None):
        self.extrusion_global_multiplier = extrusion_global_multiplier
        self.start_at_layer = start_at_layer
        self.layers_to_ignore = layers_to_ignore
        self.verbosity = verbosity
        self.progress_callback = progress_callback
        self.yield_objects = False
        self.justcalculate = False # If True, just perform calculations but doesn't generate the brick-layering
        self.experimental_arcflick = False # If True, turns On "ARC Flick" after wiping, an experiment to free the nozzle from stringing
        self.travel_threshold = 1.5 #mm If the distance to move between points is smaller than this, don't retract or wipe, just move.
        self.wipe_distance = 2.0  #mm Total distance we want to wipe
        self.retract_before_wipe = 0.8 # Float between 0 and 1 - if 0 all the retraction will be done in a wipe. If 1, all the retaction is without a wipe.
        self.travel_zhop = 0.4 #mm Vertical distance to move up when traveling to distante points
        self.retracted = 0.0 #mm Like a 'Debt' value: how much it has been retracted so far, for detraction to restitute later
        self.last_travelled_gcode_line = None # Experiment...
        self.last_internalperimeter_state = None # Experiment...
        self.last_internalperimeter_xy_line = None # Experiment...
        self.last_noninternalperimeter_state = None # Experiment...
        self.last_noninternalperimeter_xy_line = None # Used to re-conciliate the moved lines to their new surroundings
        self.header_info = {} # Any text to be included at the beginning of the exported file
        self.enable_header = False # If turned false, won't output the Bricklayers header information to the file

    def set_progress_callback(self, callback: Callable[[dict], None]):
        """Sets the progress callback function."""
        self.progress_callback = callback

    # Processing Progress:
    # Which is delegated to an external function
    # You can write your own progress function without changing this class!
    def update_progress(self, bytesprocessed: int, text: str, linecount: int, layercount: int):
        if self.progress_callback:
            self.progress_callback({
                "bytesprocessed": bytesprocessed,
                "text": text,
                "linecount": linecount,
                "layercount": layercount,
                "verbosity": self.verbosity
            })


    @staticmethod
    def new_line_from_multiplier(myline, extrusion_multiplier):
        # Calculates the Relative Extrusion based on the absolute extrusion values of the simulator
        e_val = myline.current.e - myline.previous.e

        # Apply multipliers:
        e_val = e_val * extrusion_multiplier

        parts = myline.gcode.split()  # Split the line into components
        for i, part in enumerate(parts):
            if part.startswith("E"):  # Found the extrusion value
                parts[i] = f"E{e_val:.5f}"  # Replace only the E value
                break  # No need to keep looking
        command = " ".join(parts)  # Reconstruct the G-code line

        myline.gcode = command + "\n"
        return myline # keeps the states, just change the actual gcode string

    def set_header_info(self, dict):
        self.header_info = dict

    def gen_header_lines(self, gcodeline_wrap = True) -> list:
        """
        Args:
            gcodeline_wrap (bool): 
                - True returns a list of GCodeLine objects.
                - False returns a list of plain string lines.
        """
        t = []
        pf  = ";=="
        bar = "=============================="

        t.append(bar)
        t.append(" BrickLayers Post-Processed")
        # Loop through key/values to build header
        for key, value in self.header_info.items():
            t.append(f" {key}: {value}")     
        t.append(bar)
        t.append("")

        # Prefix each line with pf and add line breaks
        output = []
        for line in t:
            txt = f"{pf}{line}\n" if line else f"\n"
            if gcodeline_wrap:
                output.append(GCodeLine.from_gcode(txt))
            else:
                output.append(txt)
        return output

    def travel_to(self, target_state, simulator, feature, loop = None, start_state = None, z = None):
        from_gcode = GCodeLine.from_gcode # faster lookup
        gcodes = []

        travel_threshold = self.travel_threshold

        if loop is not None:
            start_pos = loop[-1].current
        elif start_state is not None:
            start_pos = start_state

        move_z = ""
        zhop = self.travel_zhop
        hopping_z = ""
        if z is not None:
            move_z = f" Z{z:.2f}"
            hopping_z = f" Z{(z + zhop):.2f}"

        if Point.distance_between_points(start_pos, target_state) < travel_threshold :
            # Simple Travel - no wipe nor retraction (very close travel)
            move = from_gcode(f"G1 X{target_state.x} Y{target_state.y}{move_z} F{int(simulator.travel_speed)} ; BRICK: Travel (no-retraction)\n") # Simple Move
            gcodes.append(move)
            self.last_travelled_gcode_line = move # last move tracking
            self.last_internalperimeter_xy_line = move
            gcodes.append(from_gcode(f"G1 F{int(target_state.f)} ; BRICK: Feed Rate (no wipe)\n")) # Simple Feed
            return gcodes

        # Retraction, Wipe, Travel, Unretraction
        if simulator.retraction_length > 0 and simulator.retraction_speed > 0:
            # Retraction:
            if simulator.wipe_speed == 0:
                retraction = simulator.retraction_length
            else:
                retraction = simulator.retraction_length * self.retract_before_wipe
            gcodes.append(from_gcode(f"G1 E-{retraction:.2f} F{int(simulator.retraction_speed)} ; BRICK: Retraction \n"))
            self.retracted = self.retracted + retraction # Retraction Debt

            # Wipe:
            if loop is not None and simulator.wipe_speed > 0 and self.retract_before_wipe < 1:
                gcodes.extend(self.wipe(loop, simulator, feature))

        # Travel:
        move = from_gcode(f"G1 X{target_state.x} Y{target_state.y}{hopping_z} F{int(simulator.travel_speed)} ; BRICK: Target Position\n")
        gcodes.append(move)
        self.last_travelled_gcode_line = move # last move tracking
        self.last_internalperimeter_xy_line = move
        if z is not None:
            gcodes.append(from_gcode(f"G1 Z{z:.2f} ; BRICK: Target Position\n"))
        
        # Unretraction:
        if self.retracted > 0 and simulator.retraction_speed > 0:
            gcodes.append(from_gcode(f"G1 E{self.retracted:.2f} F{int(simulator.retraction_speed)} ; BRICK: Unretract\n"))
            self.retracted = 0 # Cancel the Debt

        return gcodes


    def wipe(self, loop, simulator, feature):
        """
        Process a loop to generate a wiping path (repeating part of the already-printed loop while retracting).

        Populates:
            moving_points: list of points to move to.
            moving_distances: list of distances between those points.
            moving_extrusions: list of extrusion values (retractions) to match.
        """
        from_gcode = GCodeLine.from_gcode

        wipe_distance = self.wipe_distance

        # Total retraction for Wiping:
        total_extrusion_to_retract = simulator.retraction_length * (1 - self.retract_before_wipe)
        #print(f"---self.retract_before_wipe:{self.retract_before_wipe} total_extrusion_to_retract:{total_extrusion_to_retract} wipe_distance:{wipe_distance}\n")

        # Calculate how much extrusion to retract per mm traveled
        extrusion_per_mm = total_extrusion_to_retract / wipe_distance

        # Current position is the end of the last segment (current nozzle position)
        start_pos = loop[-1].current

        gcodes = []

        if Point.distance_between_points(start_pos, loop[0].previous) < 1:
            # Forward wipe: follow the loop in its normal order
            wipe_mode = 'forward'
            path = loop
        else:
            # Backward wipe: reverse the loop and walk backwards
            wipe_mode = 'backward'
            path = reversed(loop)

        # Output lists
        traveled = 0.0
        moving_points = []
        moving_distances = []
        moving_extrusions = []

        for line in path:
            if line.current.is_extruding:
                if wipe_mode == 'forward':
                    from_pos = line.previous
                    to_pos = line.current
                else:  # backward mode
                    from_pos = line.current
                    to_pos = line.previous

                segment_length = Point.distance_between_points(from_pos, to_pos)

                if segment_length <= 1e-6:
                    continue

                if traveled + segment_length >= wipe_distance:
                    needed_distance = wipe_distance - traveled
                    target_point = (
                        Point.point_along_line_forward(from_pos, to_pos, needed_distance)
                        if wipe_mode == 'forward'
                        else Point.point_along_line_backward(from_pos, to_pos, needed_distance)
                    )

                    moving_points.append(target_point)
                    moving_distances.append(needed_distance)
                    moving_extrusions.append(needed_distance * extrusion_per_mm)
                    break
                else:
                    moving_points.append(to_pos)
                    moving_distances.append(segment_length)
                    moving_extrusions.append(segment_length * extrusion_per_mm)

                    traveled += segment_length
                    cur_pos = to_pos

        # Debug output (optional, but useful during development)
        # logger.debug(f"Wipe: {len(moving_points)} points, {traveled:.3f}mm covered, {sum(moving_extrusions):.3f}mm retracted, distances: {moving_distances}, extrusions: {moving_extrusions}")

        # print(moving_points)
        # print(moving_extrusions)

        gcodes.append(from_gcode(feature.const_wipe_start)) # ";WIPE_START\n"
        gcodes.append(from_gcode(f"G1 F{int(simulator.wipe_speed)}\n"))
        move = None
        for point, extrusion in zip(moving_points, moving_extrusions):
            move = from_gcode(f"G1 X{point.x:.3f} Y{point.y:.3f} E-{extrusion:.5f} ; BRICK: Wipe \n")
            gcodes.append(move)
        if move is not None:
            self.last_travelled_gcode_line = move # last move tracking
            self.last_internalperimeter_xy_line = move
        gcodes.append(from_gcode(feature.const_wipe_end)) # ";WIPE_END\n"

        self.retracted = self.retracted + total_extrusion_to_retract # Retraction Debt

        # TODO: Incorporate the experimental_arcflick 

        return gcodes


    # TODO: salvage `experimental_arcflick` into the new wipe feature and remove this:
    def wipe_movement(self, loop, target_state, simulator, feature, z = None):
        from_gcode = GCodeLine.from_gcode

        travel_threshold = self.travel_threshold
        wipe_distance = self.wipe_distance

        stopped_pull = simulator.retraction_length * 0.8  # 80% first, stopped
        moving_pull  = simulator.retraction_length * 0.2  # 20% while travelling

        total_extrusion_to_retract = moving_pull  # Total retraction for Wiping

        # Calculate how much extrusion to retract per mm traveled
        extrusion_per_mm = total_extrusion_to_retract / wipe_distance

        # Current position is the end of the last segment (current nozzle position)
        start_pos = loop[-1].current

        gcodes = [] 

        if Point.distance_between_points(start_pos, target_state) < travel_threshold :
            gcodes.append(from_gcode(f"G1 X{target_state.x} Y{target_state.y} F{int(simulator.travel_speed)} ; BRICK: Travel (no-wipe)\n")) # Simple Move
            gcodes.append(from_gcode(f"G1 F{int(target_state.f)} ; BRICK: Feed Rate (no wipe)\n")) # Simple Feed
            return gcodes # Don't perform a wipe

        if Point.distance_between_points(start_pos, loop[0].previous) < 1:
            # Forward wipe: follow the loop in its normal order
            wipe_mode = 'forward'
            path = loop
        else:
            # Backward wipe: reverse the loop and walk backwards
            wipe_mode = 'backward'
            path = reversed(loop)

        # Output lists
        traveled = 0.0
        moving_points = []
        moving_distances = []
        moving_extrusions = []

        for line in path:
            if line.current.is_extruding:
                if wipe_mode == 'forward':
                    from_pos = line.previous
                    to_pos = line.current
                else:  # backward mode
                    from_pos = line.current
                    to_pos = line.previous

                segment_length = Point.distance_between_points(from_pos, to_pos)

                if segment_length <= 1e-6:
                    continue

                if traveled + segment_length >= wipe_distance:
                    needed_distance = wipe_distance - traveled
                    target_point = (
                        Point.point_along_line_forward(from_pos, to_pos, needed_distance)
                        if wipe_mode == 'forward'
                        else Point.point_along_line_backward(from_pos, to_pos, needed_distance)
                    )

                    moving_points.append(target_point)
                    moving_distances.append(needed_distance)
                    moving_extrusions.append(needed_distance * extrusion_per_mm)
                    break
                else:
                    moving_points.append(to_pos)
                    moving_distances.append(segment_length)
                    moving_extrusions.append(segment_length * extrusion_per_mm)

                    traveled += segment_length
                    cur_pos = to_pos


            # Debug output (optional, but useful during development)
            logger.debug(f"Wipe: {len(moving_points)} points, {traveled:.3f}mm covered, {sum(moving_extrusions):.3f}mm retracted, distances: {moving_distances}, extrusions: {moving_extrusions}")

        print(moving_points)
        print(moving_extrusions)

        zhop = self.travel_zhop
        hopping_z = ""
        if z is not None:
            hopping_z = f" Z{(z + zhop):.2f}"

        if self.experimental_arcflick:
            # wipe with cleaning flick and travel:
            gcodes.append(from_gcode(f"G1 E-{stopped_pull:.2f} F{int(simulator.retraction_speed)} ; BRICK: Retraction \n"))
            gcodes.append(from_gcode(feature.const_wipe_start)) # ";WIPE_START\n"
            gcodes.append(from_gcode(f"G1 F{int(simulator.wipe_speed)}\n"))
            for point, extrusion in zip(moving_points, moving_extrusions):
                gcodes.append(from_gcode(f"G1 X{point.x:.3f} Y{point.y:.3f} E-{extrusion:.5f} ; BRICK: Wipe \n"))
            gcodes.append(from_gcode(feature.const_wipe_end)) # ";WIPE_END\n"
            gcodes.append(from_gcode(f"G1 F{int(simulator.travel_speed)} ; BRICK: Flick Speed\n"))

            if len(moving_points) > 1:
                P = moving_points[-2]
                C = moving_points[-1]
            elif len(moving_points) == 1:
                P = start_pos
                C = moving_points[-1]
            T = target_state


            I, J, arc_command = self.cleaning_flick_arc(C.x, C.y, T.x, T.y, 1.0)
            flick = f"{arc_command} Z{(z+zhop):.2f} I{I:.3f} J{J:.3f} ; Cleaning-Flick ARC\n" # ARC going UP

            # I, J, arc_command = self.cleaning_flick_arc(C.x, C.y, T.x, T.y, 0.9) # Smaller Radius
            # flick = f"{arc_command} Z{(z+zhop):.3f} I{I:.3f} J{J:.3f} F{int(simulator.travel_speed)} ; Cleaning-Flick ARC\n" # ARC on same X-Y Plane

            gcodes.append(from_gcode(flick))
            #logger.debug(f"\n\nCleaning flick: Px:{P.x} Py:{P.y} Cx:{C.x} Cy:{C.y} Cz:{z+zhop} Tx:{T.x} Ty:{T.y} Tz:{z} \n{flick}\n")

            gcodes.append(from_gcode(f"G1 X{target_state.x} Y{target_state.y}{hopping_z} F{int(simulator.travel_speed)} ; BRICK: Target Position\n"))
            gcodes.append(from_gcode(f"G1 Z{z:.2f} ; BRICK: Target Position\n"))
            if z is not None:
                gcodes.append(from_gcode(f"G1 Z{z:.2f} ; BRICK: Target Position\n"))
            gcodes.append(from_gcode(f"G1 E{simulator.retraction_length:.2f} F{int(simulator.retraction_speed)} ; BRICK: Urnetract\n"))

        elif simulator.retraction_speed>0 and simulator.wipe_speed>0:
            # wipe with travel:
            gcodes.append(from_gcode(f"G1 E-{stopped_pull:.2f} F{int(simulator.retraction_speed)} ; BRICK: Retraction \n"))
            gcodes.append(from_gcode(feature.const_wipe_start))
            gcodes.append(from_gcode(f"G1 F{int(simulator.wipe_speed)}\n"))
            for point, extrusion in zip(moving_points, moving_extrusions):
                gcodes.append(from_gcode(f"G1 X{point.x:.3f} Y{point.y:.3f} E-{extrusion:.5f} ; BRICK: Wipe \n"))
            gcodes.append(from_gcode(feature.const_wipe_end))
            gcodes.append(from_gcode(f"G1 X{target_state.x} Y{target_state.y}{hopping_z} F{int(simulator.travel_speed)} ; BRICK: Target Position\n"))
            if z is not None:
                gcodes.append(from_gcode(f"G1 Z{z:.2f} ; BRICK: Target Position\n"))
            gcodes.append(from_gcode(f"G1 E{simulator.retraction_length:.2f} F{int(simulator.retraction_speed)} ; BRICK: Urnetract\n"))
        else:
            # travel without wiping
            gcodes.append(from_gcode(f"G1 X{target_state.x} Y{target_state.y}{hopping_z} F{int(simulator.travel_speed)} ; BRICK: Target Position\n"))
            if z is not None:
                gcodes.append(from_gcode(f"G1 Z{z:.2f} ; BRICK: Target Position\n"))
        return gcodes


    @staticmethod
    def cleaning_flick_arc(Cx, Cy, Tx, Ty, radius):
        """
        Calculates:
            - I, J offsets for the arc's center (relative to C)
            - Whether to use G2 (CW) or G3 (CCW) to exit toward T
        
        C = current position (where arc starts)
        T = target position (where the arc should aim at when leaving)
        radius = desired arc radius
        """
        # Vector from C to T
        dx = Tx - Cx
        dy = Ty - Cy
        angle_to_T = math.atan2(dy, dx)

        # Compute both possible centers (90 degrees left and right of C->T vector)
        center_cw_x = Cx + radius * math.cos(angle_to_T - math.pi / 2)
        center_cw_y = Cy + radius * math.sin(angle_to_T - math.pi / 2)

        center_ccw_x = Cx + radius * math.cos(angle_to_T + math.pi / 2)
        center_ccw_y = Cy + radius * math.sin(angle_to_T + math.pi / 2)

        # For each center, calculate the vector from center to C
        vcw_x = Cx - center_cw_x
        vcw_y = Cy - center_cw_y

        vccw_x = Cx - center_ccw_x
        vccw_y = Cy - center_ccw_y

        # Check the cross product to determine which one flows correctly toward T
        cross_cw = vcw_x * dy - vcw_y * dx
        cross_ccw = vccw_x * dy - vccw_y * dx

        if cross_cw > cross_ccw:
            # CW (G2) is the better fit
            I = center_cw_x - Cx
            J = center_cw_y - Cy
            arc_command = "G2"
        else:
            # CCW (G3) is the better fit
            I = center_ccw_x - Cx
            J = center_ccw_y - Cy
            arc_command = "G3"

        return I, J, arc_command
        #return f"{arc_command} Z{Cz:.3f} I{I:.3f} J{J:.3f} ; Cleaning-Flick ARC\n"


    @staticmethod
    def calculate_loop_depth(group_perimeter,dump=False):
        """Determines the hierarchical structure of perimeter loops in a layer.

        Identifies:
        - **Concentric Loops:** Nested perimeters forming concentric walls.
        - **Orphaned Loops:** Disconnected perimeters without containment.
        - **Hole Perimeters:** Inner perimeters defining voids.

        Builds containment trees in both direct and reverse loop order, merging results 
        to establish the offset order. Returns a `moving_order` list indicating which 
        perimeters should shift in the Brick Layers transformation.

        Args:
            group_perimeter (list): Perimeter loops.

        Returns:
            list[bool]: Boolean list marking loops for movement.
        """
        # Boolean list initialized with False for all loops
        moving_order = [False] * len(group_perimeter)

        nodes = []

        for loop_index, ploop in enumerate(group_perimeter):
            bb = GCodeStateBBox()
            for pline in ploop:
                if pline.current.is_extruding: # Only compute movements that are extruding, ignore wipes or travels
                    bb.compute(pline.current)  # compute the bounding box that surrounds the current loop
            # print(node)
            # print(bb)
            nodes.append(LoopNode(loop_index, bb, ploop))

        parents_merged = BrickLayersProcessor.build_loop_tree_bidirectional(nodes)
        if dump:
            logger.info(brick_dump("parents_merged",parents_merged))

        LoopNode.concentric = 0 # Resetting the contentric counter of loops that are tightly nested
        for parent in parents_merged:
            LoopNode.concentric+=1
            parent.propagate(moving_order, 0)

        del parents_merged

        return moving_order


    @staticmethod
    def build_loop_tree(nodes, hole=False):
        """Builds the parent-child tree structure based on bounding box containment."""
        
        parents = []  # List to store the highest-level parents

        previous_node = None

        for node_index, node in enumerate(nodes):
            if node_index == 0:
                # First node, initialize it as the first parent
                previous_node = node
            else:
                # Step 1: Check if the current node contains the previous node
                if node.boundingbox.contains(previous_node.boundingbox):
                    node.kids.append(previous_node)
                    if hole:
                        node.around_hole = True
                        previous_node.around_hole = True

                    # Step 2: Also check existing parents for further nesting
                    parents_to_remove = []
                    for parent in parents:
                        if node.boundingbox.contains(parent.boundingbox):
                            node.kids.append(parent)
                            parents_to_remove.append(parent)  # Mark for removal

                    # Remove assigned parents
                    for parent in parents_to_remove:
                        parents.remove(parent)

                else:
                    # If it does not contain the previous one, previous node is a parent
                    parents.append(previous_node)

            # Move to next node
            previous_node = node

        # The last remaining node must be a top-level parent
        parents.append(previous_node)

        return parents  # Returning this for debugging or later use

    @staticmethod
    def build_loop_tree_bidirectional(nodes, hole=False):
        """Builds the parent-child tree structure based on bounding box containment."""
        # Create a node, to act as the root of the tree
        root = LoopNode(-1,None,[])
        for node_index, node in enumerate(nodes):
            if len(node.looplines)<2:
                continue
            cur_parent=root
            completed=False            
            while not completed:
                steal_kids=[]
                new_parent=None
                for kid in cur_parent.kids:
                    
                    if node.contains_point(kid.looplines[len(kid.looplines)>>2].current):
                        steal_kids.append(kid)
                    elif kid.contains_point(node.looplines[len(node.looplines)>>2].current):
                        new_parent=kid
                #move all known contained nodes into this node
                for kid in steal_kids:
                    cur_parent.kids.remove(kid)
                    node.kids.append(kid)
                if new_parent==None:
                    #cur_parent.around_hole=node.around_hole
                    cur_parent.kids.append(node)
                    completed=True
                else:
                    cur_parent=new_parent
                    #we know this only because of input order
                    #think of better way to work out holes
                    #node.around_hole=True
 
                    
        return root.kids


    def generate_deffered_perimeters(self, myline, deffered, extrusion_multiplier, extrusion_multiplier_preview, feature, simulator, buffer):
        """Creates the new intermediate "Brick Layer" for the deffered perimeters on a higher Z, recalculating extrusions"""
        from_gcode = GCodeLine.from_gcode #cache the lookup

        if len(deffered) > 0:
            target_z = feature.z + feature.height/2
            target_z_formated = f"{target_z:.2f}"
            higher_z = feature.z + feature.height + 0.2 # Z-Hop
            higher_z_formated = f"{higher_z:.2f}"

            # if logger.isEnabledFor(logging.DEBUG):
            #     logger.debug(brick_dump("deffered_perimeters", deffered, {"gcode"}))
            #     #logger.debug(brick_dump("deffered_perimeters", deffered, {"gcode", "object"}))

            current_object = None
            previous_loop = None
            previous_perimeter = 0
            concentric_group = 0
            previous_concentric_group = 0
            should_create_moveup = False

            deffered[:] = [item for item in deffered if item] # Strip Empty (!!! why)

            # Iterate through the deffered_perimeters and add lines to the buffer_lines;
            for perimeter_index, deffered_perimeter in enumerate(deffered):
                is_first_perimeter = (perimeter_index == 0)
                is_last_perimeter = (perimeter_index == len(deffered) - 1)
                new_perimeter = True
                # This fixed some very weird fenomenom of empty deffered perimeters that I don't understand yet what caused (on 3D Benchy, height 25mm, classic generator)
                deffered_perimeter[:] = [item for item in deffered_perimeter if item] # Strips Empty lists (TODO: investigate what generates empty lists it some layers)

                for loop_index, deffered_loop in enumerate(deffered_perimeter):
                    is_first_loop = (loop_index == 0)
                    is_last_loop = (loop_index == len(deffered_perimeter) - 1)
                    new_loop = True

                    for line_index, deffered_line in enumerate(deffered_loop):
                        is_first_line = (line_index == 0)
                        is_last_line = (line_index == len(deffered_loop) - 1)
                        concentric_group = deffered_line.concentric_group
                        new_object = False

                        ##########
                        # In the beginning of the layer
                        if is_first_perimeter and is_first_loop and is_first_line:
                            xy_line_to_adjust = self.last_noninternalperimeter_xy_line
                            if xy_line_to_adjust is not None and not xy_line_to_adjust.current.is_extruding:
                                #xy_line_to_adjust.update_xy(deffered_line.previous.x, deffered_line.previous.y)
                                xy_line_to_adjust.gcode = f"G1 X{deffered_line.previous.x} Y{deffered_line.previous.y} Z{higher_z_formated} F{int(simulator.travel_speed)} ; BRICK: Travel Fix Up\n"
                                self.last_noninternalperimeter_xy_line = None
                            else:
                                should_create_moveup = True
                            if feature.current_object is not None:
                                buffer.append(from_gcode(f"{feature.const_printingobject_stop}{feature.current_object.name}\n"))
                            if not deffered_line.current.relative_extrusion:
                                # If the gcode was using absolute extrusion, insert an M83 for Relative Extrusion
                                buffer.append(from_gcode("M83 ; BRICK: Change to Relative Extrusion\n"))
                            buffer.append(from_gcode(feature.const_layer_change)) # ex: ;LAYER_CHANGE
                            buffer.append(from_gcode(f"{feature.const_layer_z}{target_z_formated}\n")) # ex: ;Z:2.4
                            buffer.append(from_gcode(f";{target_z_formated}\n")) # TODO: Will it Break Bambu Studio Preview? They don't use it...
                            buffer.append(from_gcode(f"{feature.const_layer_height}{feature.height:.2f}\n")) # ex: ;HEIGHT:0.2
                            if should_create_moveup:
                                #buffer.append(from_gcode(f"G1 Z{higher_z_formated} F{int(simulator.travel_speed)} ; BRICK: Z-Hop UP\n"))
                                buffer.extend(self.travel_to(deffered_line.previous, simulator, feature, None, deffered_line.previous, higher_z))
                            buffer.append(from_gcode(f"G1 Z{target_z_formated} F{int(simulator.travel_speed)} ; BRICK: Z-Hop Down\n"))
                            #buffer.append(from_gcode(feature.internal_perimeter_type))
                            buffer.append(from_gcode(";TYPE:Custom\n"))
                            buffer.append(from_gcode(f"{simulator.const_width}{deffered_line.current.width:.2f}\n")) # avoid thin lines from the previous layer
                        ##########

                        #logger.info(f"loop_order: {loop_order} previous_loop_order: {previous_loop_order} object: {current_object}\n")


                        if current_object is not deffered_line.object:
                            # Stops printing the previous object, begins the new one:
                            if current_object is not None:
                                buffer.append(from_gcode(f"{feature.const_printingobject_stop}{current_object.name}\n"))
                            if previous_loop is not None:
                                buffer.extend(self.travel_to(deffered_line.previous, simulator, feature, previous_loop, None, target_z))
                            else:
                                buffer.extend(self.travel_to(deffered_line.previous, simulator, feature, None, deffered_line.previous, target_z))
                            buffer.append(from_gcode(f"{feature.const_printingobject_start}{deffered_line.object.name}\n"))
                            buffer.append(from_gcode(f"G1 F{int(deffered_line.previous.f)} ; BRICK: FeedRate\n"))
                            new_object = True
                            current_object = deffered_line.object
                        elif new_loop and is_first_line:
                            if previous_loop is not None:
                                buffer.extend(self.travel_to(deffered_line.previous, simulator, feature, previous_loop, None, target_z))
                            else:
                                buffer.extend(self.travel_to(deffered_line.previous, simulator, feature, None, deffered_line.previous, target_z))  
                            buffer.append(from_gcode(f"G1 F{int(deffered_line.previous.f)} ; BRICK: FeedRate\n"))



                        # Actually adding the internal perimeter line, with a recalculated extrusion:
                        calculated_line = BrickLayersProcessor.new_line_from_multiplier(deffered_line, extrusion_multiplier)
                        buffer.append(calculated_line) # Actual Insertion of the Loop Line



                        ##########
                        # The last thing of the layer:
                        if (is_last_perimeter and is_last_loop and is_last_line and current_object is not None):
                            #"Cancel Object" Feature, stopping the very last object.
                            buffer.append(from_gcode(f"; stop printing object {current_object.name}\n"))
                        if (is_last_perimeter and is_last_loop and is_last_line and not deffered_line.current.relative_extrusion):
                            # If the gcode was using absolute extrusion, insert an M82 to return to Absolute Extrusion
                            buffer.append(from_gcode("M82 ; BRICK: Return to Absolute Extrusion\n"))
                            # Resets the correct absolute extrusion register for the next feature:
                            buffer.append(from_gcode(f"G92 E{myline.previous.e} ; BRICK: Resets the Extruder absolute position\n"))
                        ##########

                        if previous_perimeter != perimeter_index:
                            previous_perimeter = perimeter_index
                        # Reset:
                        new_loop = False
                        new_object = False
                        new_perimeter = False

                    previous_concentric_group = concentric_group  # allows to identify when should RETRACT to another non-concentric region of the perimeter 
                    previous_loop = deffered_loop
        
            deffered.clear() # Clearing the structure
            
            # Insert a safe point to continue this line:
            # TODO: Should retract before? Create a custom retraction if the next line starts further away from the end of the last deffered perimeter
            move = from_gcode(f"G1 X{myline.previous.x} Y{myline.previous.y} F{int(simulator.travel_speed)} ; BRICK: Calculated to next coordinate\n")
            buffer.append(move)
            self.last_internalperimeter_xy_line = move
            buffer.append(from_gcode(f"G1 F{int(deffered_line.previous.f)} ; BRICK: Feed Rate\n")) # Simple Feed

            # TODO: Eliminate double-travels, passing the "buffer_lines" through optimization... EDIT: maybe it is not really necessary...



    def process_gcode(self, gcode_stream):
        """
        THIS IS THE MAIN FUNCTION OF THE SCRIPT
        """
        from_gcode = GCodeLine.from_gcode #cache the lookup

        extrusion_global_multiplier = self.extrusion_global_multiplier
        start_at_layer = self.start_at_layer
        layers_to_ignore = self.layers_to_ignore
        verbosity = self.verbosity

        # Layers to not apply BrickLayers:
        if layers_to_ignore is None:
            layers_to_ignore = []

        # Feature Detector:
        # identifies the feature changes, named objects, layer height, etc.
        feature = GCodeFeature()

        # GCode Simulator:
        # simulates the movements at every parsed line, calculating position of X, Y, Z and E (yes, it supports absolute extrusion)
        # it also knows the current width applied, when it is extruding, or just stopped extruding
        simulator = GCodeSimulator()
        current_state = simulator.get_state() # capturing the current state (where the current line would take the printer) 
        previous_state = current_state        # and also the previous state (where it was by the previous line)
        
        # Progress Indication Varibles:
        bytes_received = 0

        special_accel_command = None

        # Extrusion Multipliers:
        extrusion_multiplier = extrusion_global_multiplier # keeping a separate name in case I want to change the extrusion_multiplier at some layers
        first_layer_multiplier = extrusion_global_multiplier * 1.5

        # Applying just a "fourth" of the increment on `;WIDTH:` for a more realistic preview
        # otherwhise it looks incredibly exagerated (it doesn't affect the printing)
        extrusion_multiplier_preview = (((extrusion_multiplier - 1) / 4) +1)

        # Buffers:
        buffer_lines = []  # Temporary storage for parsed line objects
        # Detections (will be turned false once are done)
        still_in_header = True
        detect_speeds = True

        # uggly flags:
        knife_activated = False
        layer_changed_during_internal_perimeter = False

        # Process the G-code
        #READING ONE LINE AT A TIME FROM A GENERATOR (the input)
        
        #loop for header stuff
        for line_number,line in enumerate(gcode_stream, start=1):
            bytes_received += len(line.encode("utf-8"))
            if still_in_header:
                if line.startswith("; perimeters extrusion width = "): # TODO: could be interesting to change WIDTH for internal perimeters (using the multiplier)
                    pass
            #update the state of the current simulator:
            simulator.parse_gcode_line(line)
            current_state = simulator.get_state()
            
            #identify feature changes in current gcode line, also using the simulator on the previous line state:
            feature.parse_gcode_line(line)

            if feature.layer_change:
                break

            myline = from_gcode(line) # Data Structure containing the GCODE ("content") of the current line
            myline.object = feature.current_object

            previous_state=current_state
            #buffer_lines.append(myline)
            if not self.yield_objects: #why buffer when we can just return things
                yield line
            else:
                yield myline
        layer_index=0
        layer_buffer=[]
        layer_islands = []
        current_loop=[]
        current_island=LoopIsland(0)
        current_layer=0
        #main loop
        for line_number,line in enumerate(gcode_stream, start=line_number):

            bytes_received += len(line.encode("utf-8"))
            #update the state of the current simulator:
            simulator.parse_gcode_line(line)
            current_state = simulator.get_state()
            
            #identify feature changes in current gcode line, also using the simulator on the previous line state:
            feature.parse_gcode_line(line)


            myline = from_gcode(line) # Data Structure containing the GCODE ("content") of the current line
            myline.object = feature.current_object

            if feature.layer_change or line.startswith(";TYPE:Custom"):
                if current_layer < start_at_layer:
                    buffer_lines.extend(layer_buffer)
                elif len(layer_islands)>0:
                    loops=[]
                    
                    for island in layer_islands:
                        loops.extend(island.loops)
                    #for ii in range(i,len(buffer_lines)):
                    #    buffer_lines.append(buffer_lines[ii])
                    logger.info(f"layer:{feature.layer-1}")
                    ### Loop Depth detection (including loops that are orphaned - and surrounding holes)
                    moving_sequence = enumerate(BrickLayersProcessor.calculate_loop_depth(loops,True))
                    buffer_index = 0
                    deffered_perimeters=[]
                    if feature.layer == start_at_layer:
                        extrusion_multiplier = first_layer_multiplier
                    else:
                        extrusion_multiplier = extrusion_global_multiplier
                    for island in layer_islands:
                        buffer_lines.extend(layer_buffer[buffer_index:island.start])
                        buffer_index=island.end
                        buffer_lines.append(from_gcode(feature.internal_perimeter_type))
                        buffer_lines.append(from_gcode(f"{feature.const_layer_height}{feature.height}\n"))

                        for loop in island.loops:
                            _,to_move=next(moving_sequence)
                            if to_move:
                                deffered_perimeters.append(loop)
                                buffer_lines.append(from_gcode(f"{simulator.const_width}{loop[-1].current.width}\n"))   # For the Preview
                            else:
                                kept_line=loop[0]
                                buffer_lines.append(from_gcode(f"G1 X{kept_line.previous.x} Y{kept_line.previous.y} F{int(simulator.travel_speed)}\n"))
                                buffer_lines.append(from_gcode(f"G1 F{int(kept_line.previous.f)} ; BRICK: Feed Rate\n")) # Simple Feed
                                # for new_line in loop:
                                #     calculated_line=BrickLayersProcessor.new_line_from_multiplier (new_line,extrusion_multiplier)
                                #     buffer_lines.append(calculated_line)
                                buffer_lines.extend(loop)
                        buffer_lines.append(from_gcode(f"G1 X{island.end_state.x} Y{island.end_state.y} F{int(simulator.travel_speed)}"))
                    buffer_lines.extend(layer_buffer[buffer_index:])
                    myline.previous=previous_state
                    myline.current=current_state
                    self.generate_deffered_perimeters(myline, [deffered_perimeters], extrusion_multiplier, extrusion_multiplier_preview, feature, simulator, buffer_lines)
                if not self.yield_objects:
                    yield from (gcodeline.to_gcode() for gcodeline in buffer_lines)
                else:
                    yield from buffer_lines
                buffer_lines.clear()
                layer_islands.clear()
                layer_buffer.clear()
                layer_index=line_number
                current_layer=feature.layer
                if line.startswith(";TYPE:Custom"):
                    break

            if detect_speeds == True: # it must begin as True - there is no default speeds (override down). It changes to False once speeds are detected
                if simulator.retraction_speed == 0 and feature.wiping :
                    simulator.retraction_speed = simulator.f
                if simulator.wipe_speed == 0 and feature.wipe_willfinish:
                    simulator.wipe_speed = simulator.f
                if simulator.detraction_speed == 0 and simulator.retraction_speed > 0 and simulator.is_extruding:
                    simulator.detraction_speed = simulator.f
                if simulator.wipe_speed > 0 and simulator.detraction_speed > 0 and simulator.retraction_speed > 0:
                    detect_speeds = False
                    # Overriding: (if you neeed)
                    #simulator.retraction_length = 1.0 #mm
                    #simulator.detraction_speed = 1800.0 #mm/sec
                    logger.debug(f"\n\n travel_speed: {simulator.travel_speed}\n wipe_speed: {simulator.wipe_speed}\n retraction_speed: {simulator.retraction_speed}\n detraction_speed: {simulator.detraction_speed}\n retraction_length: {simulator.retraction_length}\n\n")

            if feature.internal_perimeter:

                if not knife_activated and (feature.wiping or simulator.retracted < 0 or simulator.just_stopped_extruding):
                    knife_activated = True
                elif knife_activated and simulator.is_extruding and simulator.is_moving:
                    knife_activated = False
                elif knife_activated and not feature.wiping and myline.gcode.startswith("G1 F"):
                    knife_activated = False

                if feature.justgotinside_internal_perimeter:
                    current_island.set_start(line_number-layer_index,current_state)
                elif knife_activated:
                    if len(current_loop)>0:
                        current_island.append(current_loop)
                        current_loop=[]
                elif not knife_activated:
                    myline.previous = previous_state    # attach the previous simulated state to the line
                    myline.current = current_state      # attach the current  simulated state to the line
                    myline.object = feature.current_object # Reference to the Currently Printing Object, for the "Cancel Object" feature
                    current_loop.append(myline)
            elif feature.justleft_internal_perimeter:
                if len(current_island)>0:
                    current_island.set_end(line_number-layer_index-1,previous_state)
                    layer_islands.append(current_island)
                    current_island=LoopIsland(0)
                knife_activated=False
            

            previous_state=current_state
            layer_buffer.append(myline)
        #loop for remainder of file
        for line_number,line in enumerate(gcode_stream, start=line_number):

            
            bytes_received += len(line.encode("utf-8"))
            simulator.parse_gcode_line(line)
            current_state = simulator.get_state()
            
            #identify feature changes in current gcode line, also using the simulator on the previous line state:
            feature.parse_gcode_line(line)


            myline = from_gcode(line) # Data Structure containing the GCODE ("content") of the current line
            myline.object = feature.current_object

            #buffer_lines.append(myline)
            if not self.yield_objects:
                yield line
            else:
                yield myline

        if verbosity == 1 or verbosity == 2:
            self.update_progress(bytes_received, "", line_number, feature.layer)
        if verbosity == 3:
            str_feature = f"{feature.current_type:<20}"[:20]
            self.update_progress(bytes_received, f"Feature: {str_feature} GCode:{line}", line_number, feature.layer)
        deffered_perimeters.clear()
        buffer_lines.clear()

# I might ditch this to using Python's Logger for errors on a separate file...
def error_log(message, details):
    import os
    import platform
    from datetime import datetime, timezone

    error_log   = "bricklayers_error_log.txt"
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    error_log_path = os.path.join(script_dir, error_log)
    python_imp = platform.python_implementation()
    python_ver = platform.python_version()
    os_info    = f"{platform.system()} {platform.release()}"
    timestamp  = datetime.now().astimezone().isoformat()

    with open(error_log_path, "a", encoding="utf-8") as f:
        f.write("\n" * 2)
        f.write("=" * 50 + "\n")
        f.write(f"🕒 {timestamp}\n")
        f.write(f"💥 {message}\n")
        f.write(f"   BrickLayers.py {__version__}\n")
        f.write(f"   Python Interpreter: {python_imp}\n")
        f.write(f"   Python Version: {python_ver}\n")
        f.write(f"   OS: {os_info}\n\n")
        f.write(details)



def main():
    import argparse
    import tempfile
    import platform
    import shutil
    import os
    import sys
    import time


    def human_readable_size(size_bytes):
        """Converts bytes to a human-readable format (e.g., 4.2MB, 670kB)."""
        units = ["B", "kB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}PB"  # Edge case for extremely large sizes


    #
    #   Displaying Progress in the Terminal, for CLI Usage:
    #
    def get_terminal_width():
        """Get terminal width dynamically, defaulting to 80."""
        return shutil.get_terminal_size((80, 20)).columns

    def supports_ansi():
        """Detect if the terminal supports ANSI colors."""
        return sys.platform != "win32" or "WT_SESSION" in os.environ or "PYCHARM_HOSTED" in os.environ or os.environ.get("TERM_PROGRAM") == "vscode"

    if supports_ansi(): # ANSI escape codes for colors
        RED = "\033[31m"
        WHITE = "\033[37m"
        RESET = "\033[0m"
    else:
        RED = WHITE = RESET = ""  # No colors on unsupported terminals

    first_update = True  # Ensures first print behaves correctly
    input_file_size = 0 # Must know the size of the file in order to show progress correctly
    previous_progress = 0

    def update_progress(progress_data: dict):
        """Displays progress, numeric stats, and the last line read without scrolling."""
        nonlocal first_update, input_file_size, previous_progress, final_output_file

        # Unpack all values from dictionary
        bytesprocessed, text, linecount, layercount, verbosity = (
            progress_data.get(key, 0) for key in ["bytesprocessed", "text", "linecount", "layercount", "verbosity"]
        )

        progress = int((bytesprocessed / input_file_size) * 100)
        # if progress == previous_progress:
        #     return

        progress %= 101  # Auto-reset at 100%
        
        term_width = get_terminal_width()
        bar_width = term_width - 11  # Adjust width for text space
        filled = int(progress / 100 * bar_width)

        bar_color = RED if progress < 100 else WHITE
        bar = f"{bar_color}#{RESET}" * filled + "-" * (bar_width - filled)

        if not first_update:
            sys.stdout.write("\033[F\033[K" * 3)  # Move up and clear previous lines
        else:
            first_update = False  # Prevents scrolling on the first print

        size = human_readable_size(input_file_size)

        # Print updated progress info
        clean_text = text[:term_width - 10].rstrip("\n")
        sys.stdout.write(f"\r[{bar}] {progress:.2f}%\n")  # Progress Bar
        sys.stdout.write(f"Original Size: {size}  Layers: {layercount}  Lines: {linecount}\n")  # Stats
        sys.stdout.write(f"{clean_text}\n")  # G-code line

        # If progress reaches 100% and verbosity is enabled, clear the last three lines
        if progress == 100 and verbosity == 1:
            sys.stdout.write("\033[F\033[K" * 3)  # Move up and clear the last three lines
            sys.stdout.write(f"{final_output_file}\n")
            sys.stdout.write(f"Original Size: {size}  Layers: {layercount}  Lines: {linecount}\n")  # Stats

        previous_progress = progress
        sys.stdout.flush()


    def update_progress_print(progress_data: dict):
        """Demonstration of getting the progress without changing the processor"""
        global input_file_size
        print(int(progress_data["bytesprocessed"] / input_file_size * 100))


    class ErrorLoggingArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write(f"\n💥 BrickLayers error: {message}\n\n")
            self.print_usage(sys.stderr)
            sys.stderr.write("\nSee 'bricklayers_error_log.txt' for details.\n")
            error_log("Argument parsing error", message)
            sys.exit(2)

    # Auxiliar Functions to Ignore a list of Layers
    def parse_ignore_layers_from_to(value_list):
        # Converts a list of numbers into tuples of (start, end).
        if len(value_list) % 2 != 0:
            raise argparse.ArgumentTypeError("The -ignoreLayersFromTo argument must have an even number of values (pairs).")

        return [(value_list[i], value_list[i + 1]) for i in range(0, len(value_list), 2)]

    def expand_ranges(ranges):
        """Expands (start, end) tuples into a list of individual numbers."""
        expanded = set()
        for start, end in ranges:
            expanded.update(range(start, end + 1))  # Include both start and end
        return expanded


    parser = ErrorLoggingArgumentParser(
        description=f"""\
BrickLayers by Geek Detour  ({__version__})
Post-process GCode for BrickLayers Z-shifting with extrusion adjustments.
https://github.com/GeekDetour/BrickLayers

Argument names are case-insensitive, so:
- outputFile, -OUTPUTFILE, and -outputfile all work.

""",
    formatter_class=argparse.RawTextHelpFormatter,
    add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="Show this help message and exit.\n\n")
    parser.add_argument("-v", "--version", action="version", version=f"Brick Layers by Geek Detour {__version__}")
    parser.add_argument("input_file", 
                         help="\nPath to the input G-code file\n\n")
    parser.add_argument("-outputFile", 
                         help="\nPath to create a separate modified G-code file\n"
                                "Useful for converting files already on disk\n\n"
                                "If not specified, the input file content is overwritten\n"
                                "(which is how it works with a Slicer; it uses only the input_file)\n\n", default=None)
    parser.add_argument("-outputFilePostfix", nargs="?", const="_brick", default=None, 
                        help="\nIf -outputFile is not provided, the original filename is used with an appended suffix.\n"
                             "'_brick' is the default if used without a value\n\n"
                             "Example:\n"
                             "python bricklayers.py 3dbenchy.gcode -outputFilePostfix\n"
                             " -> Saves as '3dbenchy_brick.gcode'\n\n")
    parser.add_argument("-outputFolder",
                    help="\nSpecify a folder to save the modified G-code file.\n"
                         "If used with -outputFile, this option is ignored.\n"
                         "If used with -outputFilePostfix, the new filename is placed inside this folder.\n"
                         "If used alone, the original filename is used but saved in this folder.\n\n"
                         "Example:\n"
                         "python bricklayers.py 3dbenchy.gcode -outputFolder ./modified\n"
                         " -> Saves as './modified/3dbenchy.gcode'\n\n"
                         "python bricklayers.py 3dbenchy.gcode -outputFolder ./modified -outputFilePostfix\n"
                         " -> Saves as './modified/3dbenchy_brick.gcode'\n\n",
                    default=None)
    parser.add_argument("-extrusionMultiplier", type=float, default=1.05,
                        help="\nExtrusion multiplier for first layer\n"
                             "Default: 1.05x\n\n")
    parser.add_argument("-startAtLayer", type=int, default=3, 
                        help="\nPreserves the first layers\n"
                             "(default: 3). Set to 1 to start from the very first layer\n\n")
    parser.add_argument("-ignoreLayers",       type=int, nargs="*", default=[], 
                        help="\nList of individual layers to ignore.\n"
                             "Example:\n"
                             "-ignoreLayers 10 15 21\n\n")
    parser.add_argument("-ignoreLayersFromTo", type=int, nargs="*", default=[], 
                        help="\nPairs of 'start' and 'end' layers to ignore.\n"
                             "Examples:\n"
                             "-ignoreLayersFromTo 1 10 40 43\n"
                             " ignores layers 1 to 10 and also from 40 to 43\n\n"
                             "-ignoreLayersFromTo 1 5 10\n"
                             " generates an error\n\n")
    parser.add_argument("-enabled", type=int, choices=[0, 1], default=1, 
                        help="\nOptions:\n"
                               "0: Disable\n"
                               "1: Enable (default)\n\n")
    parser.add_argument("-verbosity",  type=int, choices=[0, 1, 2, 3], default=2, 
                        help="\nOptions:\n"
                               "0: No Output\n"
                               "1: Just Filenames\n"
                               "2: Progress (default)\n"
                               "3: Progress all lines, a bit slower\n\n")
    parser.add_argument("-noHeader", action="store_true",
                        help="\nSkip adding BrickLayers header to your G-code\n"
                               "Recommended only for automation\n"
                               "(header is helpful for debugging)\n\n")
    parser.add_argument("-noLogging", action="store_true",
                        help="\nDisables any Logging from BrickLayers\n"
                               "(NOT FULLY IMPLEMENTED YET)\n\n")

    args = parser.parse_args()

    # Create a case-insensitive argument dictionary (keys are lowercase, values stay unchanged)
    args_dict = {k.lower(): v for k, v in vars(args).items()}  # Preserve user-provided values


    if not args_dict["nologging"]:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_file_path = os.path.join(script_dir, "bricklayers_log.txt")
        logging.basicConfig(
            filename=log_file_path,
            filemode="a", # change to "w" if you only want to see the latest run.
            level=logging.DEBUG,
            format="%(asctime)s - %(message)s"
        )


    error_marker = "❌ Error: " if sys.stderr.encoding.lower() == "utf-8" else "[ERROR] "

    def gcode_opener(path, flags):
        with open(path, "rb") as f:  # Open in binary mode
            header = f.read(4)  # Read the first 4 bytes
        if header == b"GCDE":  # Use byte-string for direct comparison
            print(f"{error_marker}The file '{path}' is a binary G-code file, which is not supported. Disable Binary G-code in your slicer settings.", file=sys.stderr)
            error_log("Binary G-code file", path)
            sys.exit(1)  # Exit immediately
        return os.open(path, flags)  # Open the file descriptor only if valid


    # Only process the file if Brick Layers if enabled
    if args_dict["enabled"] > 0:


        input_file = args_dict["input_file"]

        # Detect if the input file is in a temp directory (Windows 11 adjusted)
        normalized_input_file = input_file.replace("\\", "/").lower()  # Normalize slashes for consistency

        # Detect if the input file is in a temp directory
        # We are implying the script is being used by the Slicer, not a command line
        is_uploading = any(tmp in normalized_input_file for tmp in [
            "/tmp/",
            "/temp/",
            "/appdata/local/temp",
            "/temp."
        ])

        # Convert -ignoreLayersFromTo list into tuples of 2
        ignore_ranges = parse_ignore_layers_from_to(args.ignoreLayersFromTo)

        # Expand ranges into a set of individual layers
        expanded_ignore_layers = expand_ranges(ignore_ranges)

        # Merge both ignoreLayers and expanded range layers into a single set
        final_ignored_layers = sorted(set(args.ignoreLayers) | expanded_ignore_layers)  # Union of both sets

        # Determine output file name
        is_temp_file = False
        output_folder = args_dict["outputfolder"]  # New argument
        output_file = args_dict["outputfile"]
        postfix = args_dict["outputfilepostfix"]

        # STRICT VALIDATION: Ensure outputFolder exists and is a directory
        if output_folder:
            if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
                print(f"{error_marker}The specified output folder '{output_folder}' does not exist or is not a valid directory.", file=sys.stderr)
                sys.exit(1)  # Exit immediately

        if output_file:
            # If user provided -outputFile, use it directly and ignore -outputFilePostfix and -outputFolder
            final_output_file = output_file
        else:
            # Extract base name and extension from input file
            base_name, ext = os.path.splitext(os.path.basename(input_file))

            if postfix:
                # Append the postfix to the filename if provided
                base_name += postfix

            final_output_file = f"{base_name}{ext}"

            if output_folder:
                # Save modified file inside the specified output folder
                final_output_file = os.path.join(output_folder, final_output_file)
            else:
                # Save in the same directory as input_file
                final_output_file = os.path.join(os.path.dirname(input_file), final_output_file)

        # If no outputFile or outputFilePostfix was specified, create a temporary file
        if not output_file and not postfix:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".gcode")
            final_output_file = temp_file.name
            is_temp_file = True

        # FINAL VALIDATION: Ensure `final_output_file` is correctly assigned
        if final_output_file is None:
            print(f"{error_marker} Output file could not be determined! Check your arguments.", file=sys.stderr)
            sys.exit(1)


        if is_uploading:
            verbosity = 0
        else:
            verbosity = args_dict["verbosity"]

        if verbosity == 1:
            print(input_file)


        # Setting up the BrickProcessor:
        processor = BrickLayersProcessor(
            extrusion_global_multiplier=args_dict["extrusionmultiplier"],
            start_at_layer=args_dict["startatlayer"],
            layers_to_ignore=final_ignored_layers,
            verbosity=verbosity
        )
        processor.experimental_arcflick = False
        processor.set_progress_callback(update_progress)  # Full-fledged terminal progress indicator
        #processor.set_progress_callback(update_progress_print) # Super simple progress-indicator example


        # Detect interpreter
        python_imp = platform.python_implementation()
        python_ver = platform.python_version()
        os_info    = f"{platform.system()} {platform.release()}"
        IS_CPYTHON = python_imp == "CPython"
        IS_PYPY    = python_imp == "PyPy"

        # !! HEADER PRIVACY CONCERNS !!
        #
        # Certain information is very useful for debugging
        # but could accidentally expose sensitive user data:
        #
        # - Interpreter Path: Can reveal usernames or computer-specific info
        # - Script Arguments: Might contain file paths or other sensitive details
        # - Input/Output Filenames: May identify personal projects or users
        #
        # DO NOT add sensitive information to the header.
        # Keep the following list minimal, generic, and privacy-safe:
        header_info = {
            "Script Version"       : __version__,
            "Python Interpreter"   : python_imp,
            "Python Version"       : python_ver,
            "OS"                   : os_info,
            "Input Source"         : "Slicer" if is_uploading else "Command Line",
            "Starting at Layer"    : args_dict["startatlayer"],
            "Ignored Layers"       : final_ignored_layers,
            "Extrusion Multiplier" : args_dict["extrusionmultiplier"]
        }
        processor.set_header_info(header_info)
        processor.enable_header = not args_dict["noheader"]

        if verbosity > 1:
            import io
            if os.name == "nt":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleOutputCP(65001)  # Force UTF-8 Code Page
                sys.stdout.reconfigure(encoding="utf-8")
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

            # Output Parameters to be used:
            print("\n")
            print(f"▁▃▅▆ Brick Layers ▆▅▃▁  ({__version__})\n")
            print(" Input File:           ", input_file)
            print(" Output File:          ", final_output_file)
            print(" Extrusion Multiplier: ", args_dict["extrusionmultiplier"])
            print(" Layer to Start:       ", args_dict["startatlayer"])
            print(" Layers to Ignore:     ", final_ignored_layers)
            print(" Enabled:              ", args_dict["enabled"])
            print(" Verbosity:            ", args_dict["verbosity"])
            print(" Include Header:       ", "No" if args_dict["noheader"] else "Yes")
            print(" Logging:              ", "No" if args_dict["nologging"] else "Yes")
            print(" Python Interpreter:   ", python_imp)
            print(" Python Version:       ", python_ver)
            print(" OS:                   ", os_info)
            print("\n")

        logger.debug(input_file)
        logger.debug(final_output_file)

        input_file_size = os.path.getsize(input_file)

        if verbosity > 0:
            # Setup optional memory tracking
            if IS_CPYTHON:
                import tracemalloc
                tracemalloc.start()
            else:
                tracemalloc = None  # No-op for PyPy, Jython, etc.
            # Start timing
            start_time = time.time()

        # print(input_file)
        # print(final_output_file)

        # Open the input and output files using Generators:
        with open(input_file, 'r', encoding="utf8", newline="", opener=gcode_opener) as infile, open(final_output_file, 'w', encoding="utf-8", newline="\n") as outfile:
            # Pass the file generator (line-by-line) to process_gcode
            gcode_stream = (line for line in infile)  # Efficient generator

            # Process G-code using the generator
            processed_gcode = processor.process_gcode(gcode_stream)  # Generator output

            # Write processed G-code to the output file
            for processed_line in processed_gcode:
                if processed_line is not None: # TODO: why does some people get a None line?! 
                    outfile.write(processed_line)
    

        # If using a temporary file, replace the original input_file
        if is_temp_file:
            MAX_RETRIES = 10  # Number of times to retry
            WAIT_TIME = 0.2   # Time in seconds between retries
            for attempt in range(MAX_RETRIES):
                try:
                    shutil.move(final_output_file, input_file)  # Replace original file with modified G-code
                    break  # If successful, exit the loop
                except Exception:
                    try:
                        with open(final_output_file, "r", encoding="utf-8", newline="") as temp_f, open(input_file, "w", encoding="utf-8", newline="\n") as input_f:
                            input_f.write(temp_f.read())
                        break  # If successful, exit the loop
                    except Exception:
                        print(f"⚠️ Write failed, retrying in {WAIT_TIME} sec...", file=sys.stderr)
                        time.sleep(WAIT_TIME)  # Wait before retrying
            else:
                print("ERROR: Could not output the file after multiple attempts.")
                sys.exit(1)  # Exit with error if all retries fail


        if verbosity > 0:

            end_time = time.time()
            elapsed_time = end_time - start_time

            if IS_CPYTHON and tracemalloc:
                current, peak = tracemalloc.get_traced_memory()
                print(f"Peak memory usage: {peak / 1024 / 1024:.2f} MB")
            elif IS_PYPY:
                try:
                    import resource
                    rusage = resource.getrusage(resource.RUSAGE_SELF)
                    if platform.system() == "Darwin":
                        print(f"Memory usage (from resource): {rusage.ru_maxrss / 1024 / 1024:.2f} MB")  # macOS fix
                    else:
                        print(f"Memory usage (from resource): {rusage.ru_maxrss / 1024:.2f} MB")  # Linux
                except (ImportError, AttributeError):
                    #print("Memory reporting not available for PyPy on this platform.")
                    pass

            print(f"Execution time: {elapsed_time:.2f} seconds")
            print("\n")


    else:
        print("⚠️ Brick Layers is disabled (-enabled 0). No modifications applied.")


if __name__ == "__main__":
    import sys

    try:
        main()
    except Exception:
        tb = traceback.format_exc()  # Capture immediately

        # Print full traceback to screen
        print(f"\n💥 Unexpected runtime error!\n\n", file=sys.stderr)
        print(tb, file=sys.stderr)
        print(f"\nSee 'bricklayers_error_log.txt' for a saved copy.", file=sys.stderr)
        error_log("Unexpected runtime error!", tb)
        sys.exit(1)
