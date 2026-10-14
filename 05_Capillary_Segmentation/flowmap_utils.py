from plantcv import plantcv as pcv
import os
import glob
import cv2
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import UnivariateSpline, interp1d
from scipy.ndimage import map_coordinates
from skimage.transform import radon

def unique_pts(pts):
    unique_pts = []
    for pt in pts:
        pt = list(pt)
        if pt not in unique_pts:
            unique_pts.append(pt)
    return np.array(unique_pts)
# resmaple path to eaqual distance
def resample_even_pts(path, spacing=1., num_pts=None):
    if isinstance(path, np.ndarray):
        if path.shape[0] == 2:
            path = path.T
    path = unique_pts(path).astype(np.float32)
    length = np.cumsum(np.sqrt(np.sum(np.diff(path, axis=0)**2, axis=1)))
    length = np.insert(length, 0, 0)    
    f = interp1d(length, path, kind='cubic', axis=0, fill_value='extrapolate')
    if num_pts is None:
        num_pts = int(np.round(max(length)/spacing))+1 
    dists_new = np.linspace(0, max(length), num_pts) #np.arange(0, max(length), spacing)
    path_new = f(dists_new)#.astype(np.int32)
    return path_new
# smooth mask contour
def smooth_mask(mask, epsilon_f = 0.002):
    mask_image = np.zeros_like(mask, dtype=np.float32)
    contours, _ = cv2.findContours(mask,cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    # contours = [contour[::5,:,:] for contour in contours]
    contours  =[np.array(resample_even_pts(contour[:,0], 30.))[:,None,:] for contour in contours]
    contours  =[np.array(resample_even_pts(contour[:,0], 1. ))[:,None,:].astype(np.int32) for contour in contours]
    contours_smooth = [cv2.approxPolyDP(contour, epsilon=epsilon_f*cv2.arcLength(contour,True), closed=True) for contour in contours]
    mask_image = cv2.drawContours(mask_image, contours_smooth, -1, 1, -1).astype(np.float32)
    return mask_image

def distance(P1, P2):
    """
    This function computes the distance between 2 points defined by
    P1 = (x1,y1) and P2 = (x2,y2) 
    """

    return ((P1[0] - P2[0])**2 + (P1[1] - P2[1])**2) ** 0.5

def distance_to_path(P, path):
    """
    This function computes the distance between a point P = (x,y) and a path
    defined by a list of points path = [ [x1, y1], [x2, y2] , ...] 
    """

    return min([distance(P, p) for p in path])

def smooth_path(path, spacing=30.):
    path = resample_even_pts(path, spacing=spacing)
    path = resample_even_pts(path, spacing=1.)
    return path

def sort_path(coords, start=None, smooth = 1., spacing=1.):
    """
    This function finds the nearest point to a point
    coords should be a list in this format coords = [ [x1, y1], [x2, y2] , ...] 
    """
    coords = unique_pts(coords)
    coords = [list(p) for p in coords]
    if start is None:
        start = coords[0]
    if type(start) != list:
        start = start.tolist()
    
    pass_by = coords
    path = [start]
    # pass_by.remove(start)
    while pass_by:
        nearest = min(pass_by, key=lambda x: distance(path[-1], x))
        path.append(nearest)
        pass_by.remove(nearest)
    if smooth>1.:
        path = resample_even_pts(path, spacing=smooth)     
    path = resample_even_pts(path, spacing=spacing)
    return path

def path_to_img(path, img_shape=None, img=None, value=1):
    if img is not None:
        img = img.copy()
    else:
        img = np.zeros(img_shape, dtype=np.uint8)
    path = np.array(path, dtype=np.int32)
    img[path[:,1], path[:,0]] = value
    return img

def img_to_path(img):
    ''' points: [X,Y]'''
    path_unsorted = np.array(np.where(img>0)).squeeze().T[:,::-1]
    return path_unsorted.astype(np.float32)

def skeleton_prunnning(skeleton, mask, len_thresh=0):
    # get all segment edges
    pruned_skel, seg_img, edge_objects = pcv.morphology.prune(skel_img=skeleton, size=0, mask=mask)
    # sort edges by length
    lengths = [len(edge) for edge in edge_objects]
    main_edges = [np.array(edge_objects[i]).squeeze() for i in np.argsort(lengths)[::-1] if lengths[i]>=len_thresh]
    # plot the edges
    skel_out = np.zeros_like(mask, dtype=np.uint8)
    for i, edge in enumerate(main_edges):
        skel_out = path_to_img(edge, img=skel_out, value=i+1)
    return main_edges, skel_out

def detect_tip_pts(edge_map, vis=False):
    pcv.params.debug = 'noplot'
    tips = pcv.morphology.find_tips(skel_img=edge_map, mask=edge_map)
    tips = img_to_path(tips)
    if vis:
        fig_tip = plt.figure()
        ax = fig_tip.add_subplot(111)
        ax.imshow(edge_map, cmap='gray')
        for i, tip in enumerate(tips):
            plt.scatter(tip[0], tip[1], c='r', s=20)
            plt.text(tip[0]+10, tip[1], f'Id:{i}', c='r', fontsize=12)
    return tips

# get flow map along centerlines
def extend_path(path, time_window=5):
    path = np.array(path).copy()
    HTW = time_window // 2
    grads = np.diff(path, axis=0)
    # extralopate for the first and last point
    grads = np.concatenate([grads[:HTW][::-1], grads, grads[-HTW:][::-1]])
    extrapolated_path = np.concatenate([np.array([[0,0]]), np.cumsum(grads, axis=0)], axis=0)

    # print(len(extrapolated_path), len(path))
    extrapolated_path += path[0] - extrapolated_path[HTW]
    return extrapolated_path

def extend_path_tail(path, TW=5):
    path = np.array(path).copy()
    grads = np.diff(path, axis=0)
    # extralopate for the first and last point
    grads = np.concatenate([grads, grads[-TW:][::-1]])
    extrapolated_path = np.concatenate([np.array([[0,0]]), np.cumsum(grads, axis=0)], axis=0) + path[0]
    return extrapolated_path

def get_tangent_direction(path, time_window=5):
    ex_path = extend_path(path, time_window).astype(np.float32)
    tangent_angles = []
    for i in range(0, len(ex_path)-time_window+1):
        tangent = ex_path[i+time_window-1] - ex_path[i]
        tangent /= np.linalg.norm(tangent)
        tangent_angles.append(tangent)
    tangent_angles = np.array(tangent_angles)
    return tangent_angles

def get_normal_direction(path, time_window=5):
    tangent_angles = get_tangent_direction(path, time_window)
    normal_angles = np.stack([-tangent_angles[:,1], tangent_angles[:,0]], axis=1)
    return normal_angles

def direction_to_flow(directions, path, img_shape):
    path = np.array(path)
    flow = np.zeros(img_shape+(2,), dtype=np.float32)
    for i, d in enumerate(directions):
        flow[int(path[i,1]), int(path[i,0])] = d #/ np.linalg.norm(d)
    return flow

def get_vessel_walls(sorted_edge, norms, mask, r):
    # plot the normal lines
    norm_start, norm_end = norms[0], norms[-1]
    CL_start, CL_end, CL_mid = sorted_edge[0], sorted_edge[-1], sorted_edge[len(sorted_edge)//2]
    norm_start1, norm_start2 = CL_start - r*norm_start, CL_start + r*norm_start
    norm_end1, norm_end2 = CL_end - r*norm_end, CL_end + r*norm_end

    # remove ends and merging parts for better flow estimation
    seg_mask = mask.copy() #cv2.erode(mask.copy(), np.ones((3,3), np.uint8), iterations=1)
    bound_mask = np.zeros_like(mask)
    bound_mask = cv2.line(bound_mask, tuple(norm_start1.astype(np.int32)), tuple(norm_start2.astype(np.int32)), 1, 2)* seg_mask
    bound_tips = detect_tip_pts(pcv.morphology.skeletonize(mask=bound_mask))
    bound_mask = cv2.line(bound_mask, tuple(norm_end1.astype(np.int32)), tuple(norm_end2.astype(np.int32)), 1, 2)* seg_mask
    seg_mask = seg_mask - bound_mask
    # plt.imshow(seg_mask, cmap='gray')
    # plt.show()
    # get the valid area
    ret, seg_mask = cv2.connectedComponents(seg_mask.astype(np.uint8))
    valid_id = seg_mask[int(CL_mid[1]), int(CL_mid[0])]
    seg_mask = (seg_mask==valid_id).astype(np.uint8) + bound_mask
    # extract the path of vessel walls
    # seg_mask = cv2.dilate(seg_mask, np.ones((3,3), np.uint8), iterations=1)
    vessel_walls, _ = cv2.findContours(seg_mask.astype(np.uint8),cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    vessel_walls = [vessel.squeeze() for vessel in vessel_walls][0]
    vessel_wall_map = np.zeros_like(mask).astype(np.float32)
    vessel_wall_map = cv2.drawContours(vessel_wall_map, [vessel_walls], -1, 1, 1)
    vessel_wall_map = vessel_wall_map * (1-bound_mask)
    ret, vessel_wall_map = cv2.connectedComponents(vessel_wall_map.astype(np.uint8))
    vessel_walls = [img_to_path((vessel_wall_map==i).astype(np.uint8)) for i in range(1, ret)]
    # print(len(vessel_walls))
    # trim centerline
    CL = []
    for pt in sorted_edge:
        if bound_mask[int(pt[1]), int(pt[0])]==0:
            CL.append(pt)
    # print(len(sorted_edge),len(CL))
    # sort vessel wall path
    for wi, wall in enumerate(vessel_walls):
        dists = [distance_to_path(p, wall) for p in bound_tips]
        start_pt = bound_tips[np.argmin(dists)]
        wall_sorted = sort_path(wall, start=start_pt, smooth=20., spacing=1.)
        wall_sorted = resample_even_pts(wall_sorted, 1., num_pts=len(CL))
        vessel_walls[wi] = wall_sorted.astype(np.int32)
    contour = np.concatenate([vessel_walls[0], vessel_walls[1][::-1]], axis=0)
    seg_mask = np.zeros_like(mask)
    cv2.fillPoly(seg_mask, [contour.astype(np.int32)], 1)
    return seg_mask, vessel_walls, np.array(CL)

def get_flow_direction(path, time_windows):
    assert type(time_windows) == list
    assert type(time_windows[0]) == int
    ex_path = extend_path_tail(path, np.max(time_windows)).astype(np.float32)
    tangent_angles = []
    for i in range(0, len(path)):
        tangent = ex_path[i+time_windows[i]-1] - ex_path[i]
        tangent /= (np.linalg.norm(tangent)+1e-5)
        tangent_angles.append(tangent)
    tangent_angles = np.array(tangent_angles)
    return tangent_angles

def closest_pt(node, nodes):
    nodes = np.asarray(nodes)
    dist_2 = np.sum((nodes - node)**2, axis=1)
    return np.argmin(dist_2)

def propagate_flow(flow, path, mask):
    flow_prop = flow.copy()
    mask = mask.astype(np.float32)
    path_ori = path_to_img(path, img_shape=mask.shape)
    # smooth the flow along the path
    flow_prop = cv2.filter2D(flow_prop.copy(), -1, np.ones((7,7))) / (cv2.filter2D(path_ori.copy(), -1 ,np.ones((7,7)))[:,:,None]+1e-5)
    # normalize the flow
    flow_prop *= path_ori[:,:,None].repeat(2, axis=2).astype(np.float32)
    flow_prop = flow_prop / (np.linalg.norm(flow_prop, axis=2)[:,:,None]+1e-5)
    # start to popagate the flow to fill the mask
    old_pts = path.copy()
    while np.sum(mask * (1-path_ori)) > 0:
        # generate propagation ROI
        path_dilate = cv2.dilate(path_ori, np.ones((3,3), np.uint8), iterations=1) * mask
        path_prop = path_dilate - path_ori
        # stop when propagation is done
        if np.sum(path_prop) == 0:
            break
        new_pts = np.argwhere(path_prop)[:,::-1]
        # extrapolate flow
        new_flow = (cv2.filter2D(flow_prop.copy(), -1, np.ones((7,7)))) / ((cv2.filter2D(path_ori.copy(), -1 ,np.ones((7,7))))[:,:,None].repeat(2, axis=2)+1e-5)
        
        for new_pt in new_pts:
            new_dir = new_flow[new_pt[1], new_pt[0]]
            # normalize the flow
            flow_prop[new_pt[1], new_pt[0]] = new_dir / (np.linalg.norm(new_dir)+1e-5)
        # update path
        path_ori = path_dilate
        old_pts = new_pts
    return flow_prop

def propagate_velocity(velocity, path, mask, kernel=(5,5)):
    velo_prop = velocity.copy()
    mask = mask.astype(np.float32)
    path_ori = path_to_img(path, img_shape=mask.shape)
    # smooth the flow along the path
    velo_prop = cv2.filter2D(velo_prop.copy(), -1, np.ones(kernel)) / (cv2.filter2D(path_ori.copy(), -1 ,np.ones(kernel))+1e-5)
    velo_prop *= path_ori.astype(np.float32)
    # start to popagate the flow to fill the mask
    old_pts = path.copy()
    while np.sum(mask * (1-path_ori)) > 0:
        # generate propagation ROI
        path_dilate = cv2.dilate(path_ori, np.ones((3,3), np.uint8), iterations=1) * mask
        path_prop = path_dilate - path_ori
        # stop when propagation is done
        if np.sum(path_prop) == 0:
            break
        new_pts = np.argwhere(path_prop)[:,::-1]
        # extrapolate flow
        new_velo = (cv2.filter2D(velo_prop.copy(), -1, np.ones(kernel))) / ((cv2.filter2D(path_ori.astype(np.float32).copy(), -1 ,np.ones(kernel)))+1e-5)
        for new_pt in new_pts:
            velo_prop[new_pt[1], new_pt[0]] = new_velo[new_pt[1], new_pt[0]]
        # update path
        path_ori = path_dilate
        old_pts = new_pts
    return velo_prop

