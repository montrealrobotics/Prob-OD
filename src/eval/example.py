"""
    Simple Usage example (with 3 images)
"""
from mean_average_precision.detection_map import DetectionMAP
from mean_average_precision.utils.show_frame import show_frame
import numpy as np
import matplotlib.pyplot as plt

pred_bb1 = np.array([[0.880688, 0.44609185, 0.95696718, 0.6476958],
                     [0.84020283, 0.45787981, 0.99351478, 0.64294884],
                     [0.78723741, 0.61799151, 0.9083041, 0.75623035],
                     [0.22078986, 0.30151826, 0.36679274, 0.40551913],
                     [0.0041579, 0.48359361, 0.06867643, 0.60145104],
                     [0.4731401, 0.33888632, 0.75164948, 0.80546954],
                     [0.75489414, 0.75228018, 0.87922037, 0.88110524],
                     [0.21953127, 0.77934921, 0.34853417, 0.90626764],
                     [0.81, 0.11, 0.91, 0.21]])
pred_cls1 = np.array([0, 0, 0, 1, 1, 2, 2, 2, 3])
pred_conf1 = np.array([0.95, 0.75, 0.4, 0.3, 1, 1, 0.75, 0.5, 0.8])
gt_bb1 = np.array([[0.86132812, 0.48242188, 0.97460938, 0.6171875],
                   [0.18554688, 0.234375, 0.36132812, 0.41601562],
                   [0., 0.47265625, 0.0703125, 0.62109375],
                   [0.47070312, 0.3125, 0.77929688, 0.78125],
                   [0.8, 0.1, 0.9, 0.2]])
gt_cls1 = np.array([0, 0, 1, 2, 3])

pred_bb2 = np.array([[0.6, 0.4, 0.8, 0.6],
                     [0.45, 0.24, 0.55179688, 0.35179688],
                     [0.2, 0.15, 0.29, 0.30],
                     [0.95, 0.55, 0.99, 0.66670889],
                     [0.62373358, 0.43393397, 0.82830238, 0.68219709],
                     [0.8814062, 0.8921875, 0.94453125, 0.9704688],
                     [0.8514062, 0.9121875, 0.99453125, 0.9804688],
                     [0.40, 0.44, 0.55, 0.56],
                     [0.1672115, 0.435711, 0.32729435, 0.57853043],
                     [0.18287398, 0.15450388, 0.27082703, 0.31132805],
                     [0.3713485, 0.24020095, 0.62879527, 0.48929602]])
pred_cls2 = np.array([0, 0, 0, 0, 0, 1, 1, 2, 2, 2, 2])
pred_conf2 = np.array([0.75, 0.78, 0.83, 0.42, 0.2457653,
                       0.95, 0.5, 0.81003532, 0.18837614, 0.77496605, 0.27333026])
gt_bb2 = np.array([[0.625, 0.43554688, 0.828125, 0.67382812],
                   [0.45898438, 0.25390625, 0.59179688, 0.34179688],
                   [0.18164062, 0.16015625, 0.28125, 0.31054688],
                   [0.8914062, 0.8821875, 0.95453125, 0.9804688],
                   [0.40234375, 0.44921875, 0.55078125, 0.56445312],
                   [0.16796875, 0.43554688, 0.328125, 0.578125]])
gt_cls2 = np.array([0, 0, 0, 1, 2, 2])

pred_bb3 = np.array([[0.74, 0.58, 1.0, 0.83],
                     [0.75, 0.575, 0.99, 0.83],
                     [0.57, 0.23, 1.0, 0.62],
                     [0.59, 0.24, 1.0, 0.63],
                     [0.55, 0.24, 0.33, 0.7],
                     [0.12, 0.21, 0.31, 0.39],
                     [0.1240625, 0.2109375, 0.859375, 0.39453125],
                     [2.86702722e-01, 5.87677717e-01, 3.90843153e-01, 7.14454949e-01],
                     [2.87590116e-01, 8.76132399e-02, 3.79709303e-01, 2.05121845e-01]])
pred_cls3 = np.array(
    [0, 0, 0, 0, 0, 1, 1, 2, 2])
pred_conf3 = np.array([0.75, 0.90, 0.9, 0.9, 0.5, 0.84,
                       0.1, 0.2363426, 0.02707205])
gt_bb3 = np.array([[0.74609375, 0.58007812, 1.05273438, 0.83007812],
                   [0.57226562, 0.234375, 1.14453125, 0.62890625],
                   [0.1240625, 0.2109375, 0.329375, 0.39453125]])
gt_cls3 = np.array([0, 0, 1])

if __name__ == '__main__':
    frames = [(pred_bb1, pred_cls1, pred_conf1, gt_bb1, gt_cls1),
              (pred_bb2, pred_cls2, pred_conf2, gt_bb2, gt_cls2),
              (pred_bb3, pred_cls3, pred_conf3, gt_bb3, gt_cls3)]
    n_class = 4

    mAP = DetectionMAP(n_class)
    for i, frame in enumerate(frames):
        print("Evaluate frame {}".format(i))
        show_frame(*frame)
        mAP.evaluate(*frame)

    mAP.plot()
    plt.show()
    #plt.savefig("pr_curve_example.png")
