#! /usr/bin/env python
# coding: utf-8

# This is pos controller for like-car robot


import math
import numpy as np
import time
import rospy
import tf
from geometry_msgs.msg import Twist, Pose, TwistStamped, PoseStamped
from geometry_msgs.msg import Twist
from dynamic_reconfigure.server import Server
from rc_bringup.cfg import PoseControllerConfig
from rc_car_msgs.msg import CarPose

#value
velocity = float()
cmd_vel_msg = Twist()
current_pose = Pose()
current_course = float()
goal_pose = Pose()

init_flag = False
max_vel = 1.1 # m/s
min_vel = -1.5 # m/s
max_angle = 25

finish_flag = True
goal_tolerance = 0.2
dist=0.0

#topics
cmd_vel_topic = "/cmd_vel"
vel_topic = "/mavros/local_position/velocity"
goal_topic = "/goal"
pose_topic = "/mavros/local_position/pose"

#reg_functions
v_des=0.0
Ev=0.0
Erot=0.0
upper_limit_of_ki_sum=0.0
lower_limit_of_ki_sum=0.0

u_v=0.0
u_rot=0.0
plot_x=[0]
plot_y=[0]
v=0.0
sumErot=0
sumEv=0
distance=0

#trap function for velocity
def trap_profile_linear_velocity(x, xy_des, v_max): 
    d = np.sqrt((x.x - xy_des.position.x) ** 2 + (x.y - xy_des.position.y) ** 2)
    if d <= 1:
        v_des = -d / (d - 1)
    else:
        v_des = v_max
    return v_des

#rotatin servo regulator
def rot_controller(Erot,Erot_old,sumErot,dT):
    kp = 0.9
    ki = 0.00258
    kd = 0.00477 
    u_rot = kp * Erot + ki * sumErot + kd *(Erot-Erot_old) / dT
    return u_rot

#velocity motor regulator
def velocity_controller(Ev, Ev_old,sumEv, dT):
    kp = 0.1
    ki = 0.87
    kd = 0.001
    u_v = kp * Ev + ki * sumEv + kd *(Ev-Ev_old) / dT
    return u_v
#get distance to goal
def get_distance_to(a,b):
    """
    get distance to goal point
    :type a: Pose
    :type b: Pose
    :type dist: float
    :param a: current pose
    :param b: goal pose
    :param dist: distance
    :return: dist
    """
    pos = np.array([[b.position.x - a.position.x],
                    [b.position.y - a.position.y]])
    dist = np.linalg.norm(pos)
    return dist

def main():
    global dt, current_pose, current_course, goal_pose, cmd_vel_msg , u_v, u_rot, Ev, Erot,sumErot,sumEv, plot_x,plot_y, v_des, leinght_v,leinght_rot,v , finish_flag, goal_tolerance, dist, upper_limit_of_ki_sum, lower_limit_of_ki_sum
    dist=get_distance_to(current_pose, goal_pose)
    #car brake and PID reconfiguration to zero after destination point
    if (abs(dist) < goal_tolerance):
        finish_flag = True
        Ev=0
        Ev_old=0
        sumEv=0
        Erot=0
        Erot_old=0
        sumErot=0

    v_des=trap_profile_linear_velocity(current_pose.position,goal_pose,max_vel)
    dx=(current_pose.position.x-plot_x[0])/dt
    
    dy=(current_pose.position.y-plot_y[0])/dt
    plot_x[0]=current_pose.position.x
    plot_y[0] = current_pose.position.y
    #general velocity
    v = np.sqrt(dx**2+dy**2)
    Ev_old=Ev
    Ev=v_des-v
    sumEv=sumEv+Ev
    
    u_v=velocity_controller(Ev,Ev_old,sumEv,dt)
    #constraints for lower and upper limits
    u_v_constraints = [min_vel,max_vel]
    u_alpha_constraints=[-max_angle,max_angle]
    upper_limit_of_ki_sum=2.0
    lower_limit_of_ki_sum=-2.0
    #limit checker
    if u_v>u_v_constraints[1]:
        u_v = u_v_constraints[1]
    elif u_v<u_v_constraints[0]:
        u_v = u_v_constraints[0]
    Erot_old=Erot

    Erot=np.arctan2(goal_pose.position.y-current_pose.position.y,goal_pose.position.x-current_pose.position.x)-current_course 
    sumErot=sumErot+Erot
    #if (abs(np.degrees(Erot))>90):
    #    u_v=min_vel

    u_rot = rot_controller(Erot,Erot_old,sumErot,dt)
    if u_rot>u_alpha_constraints[1]:
        u_rot=u_alpha_constraints[1]
    elif u_rot<u_alpha_constraints[0]:
        u_rot = u_alpha_constraints[0]
    if sumErot>=upper_limit_of_ki_sum:
        sumErot=upper_limit_of_ki_sum
    if sumErot<=lower_limit_of_ki_sum:
        sumErot=lower_limit_of_ki_sum
    vel_and_angle=[u_v,u_rot]
    #output values of velocity and rotation
    vel_and_angle=[u_v,u_rot]
    cmd_vel_msg.linear.x=vel_and_angle[0]
    #print(u_v)
    cmd_vel_msg.angular.z=vel_and_angle[1]

    return cmd_vel_msg

def goal_clb(data):
    #Get goal pose
    global goal_pose, init_flag, finish_flag
    goal_pose = data.pose
    init_flag = True
    finish_flag = False

def current_pose_clb(data):
    #Get current pose from topic
    global current_pose, current_course

    current_pose = data.pose
    rot = [data.pose.orientation.x, data.pose.orientation.y, data.pose.orientation.z, data.pose.orientation.w]
    # # convert euler from quaternion
    (roll, pitch, yaw) = tf.transformations.euler_from_quaternion(rot)
    current_course = yaw

def cfg_callback(config, level):
    global max_vel, min_vel, max_angle

    max_vel = float(config["max_vel"])
    min_vel = float(config["min_vel"])
    max_angle = math.radians(float(config["max_angle"]))

    return config

def callback(config):
   rospy.loginfo("Config set to {max_vel}".format(**config))

if __name__ == "__main__":

    # init ros node
    rospy.init_node('rc_pos_controller', anonymous=True)
    rate = rospy.Rate(10)  # 10hz

    # init dynamic reconfigure server
    cfg_srv = Server(PoseControllerConfig, cfg_callback)

    # Get ros args
    if rospy.has_param('~vel_topic'):
        vel_topic = rospy.get_param('~vel_topic', vel_topic)
    if rospy.has_param('~cmd_vel'):
        cmd_vel_topic = rospy.get_param('~cmd_vel', cmd_vel_topic)
    if rospy.has_param('~goal_topic'):
        goal_topic = rospy.get_param('~goal_topic', goal_topic)
    if rospy.has_param('~pose_topic'):
        pose_topic = rospy.get_param('~pose_topic', pose_topic)

    if rospy.has_param('~max_vel'):
        max_vel = rospy.get_param('~max_vel', max_vel)
        cfg_srv.update_configuration({"max_vel": max_vel})
    if rospy.has_param('~min_vel'):
        min_vel = rospy.get_param('~min_vel', min_vel)
        cfg_srv.update_configuration({"min_vel": min_vel})
    if rospy.has_param('~max_angle'):
        max_angle = rospy.get_param('~max_angle', max_angle)
        cfg_srv.update_configuration({"max_angle": max_angle})

    # start subscriber
    #rospy.Subscriber(vel_topic, TwistStamped, vel_clb)
    rospy.Subscriber(goal_topic, PoseStamped, goal_clb)
    rospy.Subscriber(pose_topic, PoseStamped, current_pose_clb)
    vec_pub = rospy.Publisher(cmd_vel_topic, Twist,  queue_size=10)

    listener = tf.TransformListener()
    old_ros_time = rospy.get_time()
    currentTime = 0.0
    rate.sleep()

    try:
        while not rospy.is_shutdown():
            dt = rospy.get_time() - old_ros_time
            currentTime += dt


            if(not init_flag):
                if currentTime > 1.0:
                    print("pose controller: not init")
                    currentTime =  0.0
                continue

            old_ros_time = rospy.get_time()
            cmd_vel_msg = main()

            if finish_flag:
                if currentTime > 1.0:
                    print("pose controller: finish_flag True")
                    currentTime = 0.0
                cmd_vel_msg.linear.x = 0.0
                init_flag = False

            vec_pub.publish(cmd_vel_msg) # publish msgs to the robot
            rate.sleep()

    except KeyboardInterrupt:   # if put ctr+c
        exit(0)



