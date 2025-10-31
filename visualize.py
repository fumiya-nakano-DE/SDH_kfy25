import matplotlib.pyplot as plt
import numpy as np
import time
import os
import importlib
from mpl_toolkits.mplot3d import Axes3D  # 3Dプロット用
from osc_params import get_params_full, NUM_SERVOS
import osc_modes

plt.style.use("dark_background")


def plot_make_frame(fig=None, ax=None):
    duration = 30.0  # sec
    fps = 60
    num_frames = int(duration * fps)
    num_servos = NUM_SERVOS

    def get_group_color(idx, group_size, base):
        t = 1.0 - idx / max(group_size - 1, 1)
        if base == "R":
            return (1.0, 0.1 + 0.6 * (1 - t), 0.1 + 0.6 * (1 - t))
        if base == "G":
            return (0.1 + 0.6 * (1 - t), 1.0, 0.1 + 0.6 * (1 - t))
        if base == "B":
            return (0.1 + 0.6 * (1 - t), 0.1 + 0.6 * (1 - t), 1.0)

    group_indices = [[], [], []]
    for i in range(num_servos):
        group_indices[i % 3].append(i)
    group_sizes = [len(g) for g in group_indices]

    all_vals = []
    times = np.linspace(0, duration, num_frames)
    for t in times:
        vals = osc_modes.make_frame(t, num_servos) - get_params_full().get(
            "STROKE_OFFSET", 0
        )
        all_vals.append(vals)
    all_vals = np.array(all_vals)  # shape: (num_frames, num_servos)

    mode_id = str(get_params_full().get("MODE", "1"))
    mode_info = get_params_full()["MODES"][mode_id]
    mode_name = mode_info.get("NAME", f"Mode {mode_id}")
    main_params = f"BASE_FREQ={mode_info.get('BASE_FREQ')}, PHASE_RATE={mode_info.get('PHASE_RATE')}, STROKE_LENGTH={mode_info.get('STROKE_LENGTH')}"

    if fig is None or ax is None:
        plt.close("all")
        fig = plt.figure(figsize=(14, 8))
        ax = fig.add_subplot(111, projection="3d")
    else:
        ax.cla()

    PANE_COLOR = (0.1, 0.1, 0.1)
    ax.xaxis.set_pane_color(PANE_COLOR)
    ax.yaxis.set_pane_color(PANE_COLOR)
    ax.zaxis.set_pane_color(PANE_COLOR)

    z_offset_step = 1
    for group, base in zip(range(3), ["R", "G", "B"]):
        for idx_in_group, i in enumerate(group_indices[group]):
            color = get_group_color(idx_in_group, group_sizes[group], base)
            z_offset = i * z_offset_step
            if idx_in_group == 0:
                main_color = {
                    "R": (1.0, 0.1, 0.1),
                    "G": (0.1, 1.0, 0.1),
                    "B": (0.1, 0.5, 1.0),
                }[base]
                ax.plot(
                    times,
                    all_vals[:, i],
                    zs=z_offset,
                    zdir="z",
                    color=main_color,
                    linewidth=2,
                    alpha=1.0,
                    label=f"Group {group+1} (Servo {i+1})",
                    zorder=11,
                )
            else:
                ax.plot(
                    times,
                    all_vals[:, i],
                    zs=z_offset,
                    zdir="z",
                    color=color,
                    alpha=0.5,
                    linewidth=1.0,
                    zorder=1,
                )
    ax.set_title(f"Mode {mode_id}: {mode_name} | {main_params}")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Value")
    ax.set_zlabel("Servo Index")
    ax.set_ylim(-75000, 75000)
    ax.set_zlim(-z_offset_step, num_servos * z_offset_step)
    # ax.legend()
    fig.canvas.draw()
    fig.canvas.flush_events()
    return fig, ax


def watch_and_replot():
    import osc_params

    params_path = osc_params.PARAMS_FILE
    modes_path = osc_modes.__file__
    last_params_mtime = os.path.getmtime(params_path)
    last_modes_mtime = os.path.getmtime(modes_path)
    plt.ion()
    fig = plt.figure(figsize=(14, 8))
    ax = fig.add_subplot(111, projection="3d")
    plot_make_frame(fig, ax)

    print(
        "Watching for changes in get_params_full().json or osc_modes.py. Press Ctrl+C to exit."
    )
    while True:
        try:
            plt.pause(0.1)  # Allow GUI events
            time.sleep(0.1)
            new_params_mtime = os.path.getmtime(params_path)
            new_modes_mtime = os.path.getmtime(modes_path)
            updated = False
            if new_params_mtime != last_params_mtime:
                importlib.reload(osc_params)
                globals()["params"] = get_params_full()
                last_params_mtime = new_params_mtime
                updated = True
                print(
                    "Detected get_params_full().json change, reloading and replotting..."
                )
            if new_modes_mtime != last_modes_mtime:
                importlib.reload(osc_modes)
                last_modes_mtime = new_modes_mtime
                updated = True
                print("Detected osc_modes.py change, reloading and replotting...")
            if updated:
                try:
                    fig, ax = plot_make_frame(fig, ax)
                except Exception as e:
                    print(f"Error during replot: {e}")
        except KeyboardInterrupt:
            print("Stopped.")
            break


if __name__ == "__main__":
    watch_and_replot()
