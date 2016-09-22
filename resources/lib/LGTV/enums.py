class RemoteButton(object):
    HOME = "HOME"
    BACK = "BACK"
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    MODE_3D = "3D_MODE"

class Display3dMode(object):
    ERROR = -1
    OFF = 0
    CONVERT_2D_TO_3D = 1
    SIDE_SIDE_HALF = 2
    TOP_BOTTOM = 3
    CHECK_BOARD = 4
    FRAME_SEQUENTIAL = 5
    COLUMN_INTERLEAVE = 6
    LINE_INTERLEAVE_HALF = 7

    @staticmethod
    def from_string(s):
        # type: (str) -> Display3dMode
        # really bad code.
        if s == '2dto3d':
            return Display3dMode.CONVERT_2D_TO_3D
        if s == 'side_side_half':
            return Display3dMode.SIDE_SIDE_HALF
        if s == 'top_bottom':
            return Display3dMode.TOP_BOTTOM
        if s == 'check_board':
            return Display3dMode.CHECK_BOARD
        if s == 'frame_sequential':
            return Display3dMode.FRAME_SEQUENTIAL
        if s == 'column_interleave':
            return Display3dMode.COLUMN_INTERLEAVE
        if s == 'line_interleave_half':
            return Display3dMode.LINE_INTERLEAVE_HALF
        if s == '2d':
            return Display3dMode.OFF
        return Display3dMode.ERROR
