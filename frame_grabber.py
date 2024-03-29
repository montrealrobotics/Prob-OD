#!/usr/bin/env python3

from __future__ import print_function

import sys
import os
from os import listdir
from os.path import isfile, join

import numpy as np
import cv2

from third_party.pykitti import tracking

import rospy
import tf
import tf2_ros
from tf2_msgs.msg import TFMessage
from sensor_msgs.msg import Image, PointCloud2
from cv_bridge import CvBridge, CvBridgeError
from numpy_pc2 import array_to_xyzi_pointcloud2f
from geometry_msgs.msg import TransformStamped, TwistStamped, Transform
from visualization_msgs.msg import Marker, MarkerArray


def get_static_transform(from_frame_id, to_frame_id, transform):
    t = transform[0:3, 3]
    q = tf.transformations.quaternion_from_matrix(transform)
    tf_msg = TransformStamped()
    tf_msg.header.frame_id = to_frame_id
    tf_msg.child_frame_id = from_frame_id
    tf_msg.transform.translation.x = float(t[0])
    tf_msg.transform.translation.y = float(t[1])
    tf_msg.transform.translation.z = float(t[2])
    tf_msg.transform.rotation.x = float(q[0])
    tf_msg.transform.rotation.y = float(q[1])
    tf_msg.transform.rotation.z = float(q[2])
    tf_msg.transform.rotation.w = float(q[3])
    
    return tf_msg

def markers_from_labels(objects, frame, duration, stamp):
    all_boxes = MarkerArray()
    i=0
    for obj in objects:
        marker = Marker()
        marker.header.frame_id = frame
        marker.header.stamp = stamp
        marker.id = i
        marker.type = marker.CUBE
        marker.action = marker.ADD
        
        quaternion = tf.transformations.quaternion_from_euler(0, obj.ry, 0)
        marker.pose.position.x = obj.t[0]
        marker.pose.position.y = obj.t[1] - obj.h/2
        marker.pose.position.z = obj.t[2]


        marker.pose.orientation.x = quaternion[0]
        marker.pose.orientation.y = quaternion[1]
        marker.pose.orientation.z = quaternion[2]
        marker.pose.orientation.w = quaternion[3]

        marker.scale.x = obj.l
        marker.scale.y = obj.h
        marker.scale.z = obj.w

        marker.color.a = 0.5
        marker.color.r = 0.0
        marker.color.g = 1.0
        marker.color.b = 1.0

        marker.lifetime = rospy.Duration(duration)

        all_boxes.markers.append(marker)
        i+=1

    return all_boxes


class Kitti_Publisher():
    def __init__(self, data):

        self.image_topic = rospy.get_param('~image_topic', '/image_raw')
        rospy.loginfo("Publishing Images to topic  %s", self.image_topic)

        self.velodyne_topic = rospy.get_param('~velodyne_topic', '/velodyne')
        rospy.loginfo("Publishing Point cloud to topic  %s", self.velodyne_topic)

        self.ground_bbox_topic = rospy.get_param('~velodyne_topic', '/ground_3dboxes')
        rospy.loginfo("Publishing Bboxes to topic  %s", self.ground_bbox_topic)

        self.cam2_frame_id = rospy.get_param('~frame_id_cam', 'cam2')
        rospy.loginfo("Camera Frame ID set to  %s", self.cam2_frame_id)

        self.velo_frame_id = rospy.get_param('~frame_id_velo', 'velodyne')
        rospy.loginfo("Velodyne Frame ID set to  %s", self.velo_frame_id)
        
        self.image_publisher = rospy.Publisher(self.image_topic, Image, queue_size=200)
        self.velodyne_publisher = rospy.Publisher(self.velodyne_topic, PointCloud2, queue_size=200)
        self.bbox_publisher = rospy.Publisher(self.ground_bbox_topic, MarkerArray, queue_size=200)

        self.rate = rospy.get_param('~publish_rate', 5)
        rospy.loginfo("Publish rate set to %s hz", self.rate)

        self.loop = rospy.get_param('~loop', 1)
        # rospy.loginfo("[%s] (loop) Loop  %d time(s) (set it -1 for infinite)", self.__app_name, self._loop)
        
        #Generator for cam2 (left color) images
        self.images = data.cam2

        #Generator for velodyne scans
        self.velodyne_scans = data.velo

        #Generator for labels 
        self.labels = data.label
        # self.sort_files = rospy.get_param('~sort_files', True)
        # rospy.loginfo("[%s] (sort_files) Sort Files: %r", self.__app_name, self._sort_files)


        # Transform from velodyne frame to cam2 frame
        broadcaster = tf2_ros.StaticTransformBroadcaster()
        T_velo_to_cam0 = data.calib.Tr_velo_to_cam0

        self.tf_velo_to_cam0 = get_static_transform(self.velo_frame_id, 'cam0', T_velo_to_cam0)

        broadcaster.sendTransform(self.tf_velo_to_cam0)

        self.cv_bridge = CvBridge()

    def run(self):
        ros_rate = rospy.Rate(self.rate)

        while self.loop != 0:
            frame = 0
            for img, velo_scan, label in zip(self.images, self.velodyne_scans, self.labels):

                if not rospy.is_shutdown():
                    stamp = rospy.Time.now()
                    cv_image = np.array(img) # Converting PIL image to cv2
                    pc2 = array_to_xyzi_pointcloud2f(velo_scan, stamp=stamp,frame_id = self.velo_frame_id)
                    markers = markers_from_labels(label, frame='cam0', duration=1.0/self.rate, stamp=stamp)
                    # ros_msg = self.cv_bridge.cv2_to_imgmsg(cv_image, "bgr8") # bgr8 encoding gives error in image_view, hence moved to rgb8 and chaged the order above as well. 
                    ros_msg = self.cv_bridge.cv2_to_imgmsg(cv_image, "rgb8") # This encoding just tells what is the encoding of the image, here the fucntion does not change the encoding of image to the mentioned
                    # ros_msg.header.seq = join(self.image_folder, f)
                    ros_msg.header.frame_id = self.cam2_frame_id
                    ros_msg.header.stamp = stamp
                    
                    self.image_publisher.publish(ros_msg)
                    self.velodyne_publisher.publish(pc2)
                    self.bbox_publisher.publish(markers)

                    rospy.loginfo("Markers:  %s", markers)
                    rospy.loginfo("Published %s", frame)

                    frame +=1
    
                    ros_rate.sleep()

                else:
                    return

            self.loop = self.loop - 1


def main(args):
    rospy.init_node('kitti_publisher')

    base_folder = rospy.get_param('~data_folder',
                                '/home/dishank/denso-ws/src/denso/datasets/kitti_tracking/training')

    if base_folder == '' or not os.path.exists(base_folder) or not os.path.isdir(base_folder):
        rospy.logfatal("Invalid Image folder")
        sys.exit(0)
    rospy.loginfo("Reading images from %s", base_folder)
    
    sequence = rospy.get_param('~sequence', '0001')

    tracker_data = tracking(base_folder, sequence)

    kitti_publisher = Kitti_Publisher(tracker_data)
    kitti_publisher.run()


if __name__ == '__main__':
    main(sys.argv)
