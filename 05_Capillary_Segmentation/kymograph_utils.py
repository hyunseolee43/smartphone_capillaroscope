import numpy as np
import cv2
import os
import glob
from flowmap_utils import *
from scipy.ndimage import map_coordinates
from skimage.transform import radon

def get_parallel_lines(CL, norms, spacings):
    num_pts = len(CL)
    lines_array = []
    for spc in spacings:
        para_line = CL + spc*norms
        if spc!=0:
            para_line = sort_path(para_line, start=list(para_line[0]), smooth=30., spacing=1.)
            para_line = resample_even_pts(para_line, 1., num_pts = num_pts)
        lines_array.append(para_line)
    lines_array = np.array(lines_array)
    return lines_array

def load_video(video_path):
    frame_path = sorted(glob.glob(os.path.join(video_path,'*.png')))
    # load the video
    print('Loading video:', video_path)
    video = []
    for frame in frame_path:
        img = cv2.imread(frame, -1).astype(np.float32)
        video.append(img)
    video = np.array(video)
    print('Video loaded: ', video.shape)
    return video

def compenstate_kymograph(vid_centerline):
    Gt = np.mean(vid_centerline.astype(np.float32), axis=0, keepdims=True)
    Gd = np.mean(vid_centerline.astype(np.float32), axis=1, keepdims=True)
    G_bar = np.dot(Gd, Gt) / (np.mean(vid_centerline.astype(np.float32))+1e-5)

    W = vid_centerline / (Gt/np.mean(vid_centerline.astype(np.float32))+1e-5)
    W = W - np.mean(W)

    r = vid_centerline / (G_bar+1e-5)
    r = r - np.mean(r)
    return r

def kymograph_radon_transform(r, angle_range, time_window, time_step, dist_window, dist_step):
    theta = np.linspace(angle_range[0], angle_range[1], int((angle_range[1]-angle_range[0])*10), endpoint=False)
    drange, trange = r.shape[1], r.shape[0]
    vs_spacing = []
    for dist in range(0, drange-dist_window+1, dist_step):
        vs =[]
        for t in range(0, trange-time_window+1, time_step):
            if (t)%100 == 0: 
                print(f'Location along the line :{(dist + dist+dist_window-1)//2+1}/{drange}; {t:03d}/{trange}', end='\r')
            seg = r[t: t+time_window,dist:dist+dist_window]
            # print(t+time_window, vid_centerline.shape[0], seg.shape)
            sinogram = radon(seg, theta=theta, circle=False)
            deg = theta[np.argmax(np.std(sinogram, axis=0))]
            vel = np.tan(np.deg2rad(deg))
            vs.append(vel) 
        vs_spacing.append(np.array(vs))
    return vs_spacing

def interpolate_dist_profile(dists, vs_dist_ratio, drange):
    # interpolate
    f = interp1d(dists, vs_dist_ratio, kind='linear', fill_value='extrapolate')
    dists_new = np.arange(dists.min(), dists.max(), 1)
    vs_dist_ratio_new = f(dists_new)
    # extrapolate / padding
    dist_complete = np.arange(0, drange)
    vs_dist_ratio_complete = np.zeros_like(dist_complete, dtype=np.float32)
    vs_dist_ratio_complete[dists_new] = vs_dist_ratio_new
    vs_dist_ratio_complete[:dists_new.min()] = vs_dist_ratio_new[0]
    vs_dist_ratio_complete[dists_new.max():] = vs_dist_ratio_new[-1]
    return dist_complete, vs_dist_ratio_complete

# temporal interpolation
def interpolate_time_profile(time_pts, vs_tmp_avg):
    times = np.arange(time_pts.min(), time_pts.max(), 1)
    f = interp1d(time_pts, vs_tmp_avg, kind='cubic', axis=0, fill_value='extrapolate')
    vs_interp = f(times)
    return times, vs_interp