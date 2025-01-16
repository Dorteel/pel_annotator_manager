#!/home/user/pel_ws/pel_venv/bin/python
import rospy
import rospkg
import actionlib

import yaml
import cv2

from orvis.srv import ObjectDetection, ObjectDetectionRequest, ObjectDetectionResponse  # Detection service
from orvis.srv import ImageSegmentation, ImageSegmentationRequest, ImageSegmentationResponse  # Segmentation service
from orvis.msg import ImageMasks, ImageMask  # Import the segmentation message types
from orvis.srv import PromptedObjectDetection, PromptedObjectDetectionRequest, PromptedObjectDetectionResponse  # Detection service
from orvis.srv import DepthEstimation, DepthEstimationRequest, DepthEstimationResponse  # Import the necessary service types
from orvis.srv import VideoClassification, VideoClassificationRequest, VideoClassificationResponse  # Detection service
from orvis.srv import ImageToText, ImageToTextRequest, ImageToTextResponse  # Detection service

from std_msgs.msg import String
from sensor_msgs.msg import Image

# from some_msgs.msg import PickupAction, PickupGoal
# from some_msgs.srv import AnnotatorService, AnnotatorServiceRequest
import random
import os
import numpy as np
from datetime import datetime
from collections import deque

from owlready2 import get_ontology, default_world, sync_reasoner_pellet

from cv_bridge import CvBridge

class TaskSelector:
    def __init__(self):
        # Initialize the node
        rospy.init_node('task_selector')

        # Load configuration and determine service type
        self.bridge = CvBridge()
        self.load_config()
        self.prompt = String()
        self.prompt.data = "Person"

        self.last_image = None  # To store the latest image received

        # Other initializations
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.obs_graph_dir = os.path.join(os.path.dirname(self.script_dir), "obs_graphs")
        self.run_id = 'orvis_orka_' + datetime.now().strftime("%Y%m%d%H%M%S" + '.owl')
        self.save_dir = os.path.join(self.obs_graph_dir, self.run_id)

        # Initialize the ROS service
        self.video_frames = deque(maxlen=self.num_frames)

        

        # Load the ontology
        self.orka = get_ontology(self.orka_path).load()
        self.sosa = self.orka.get_namespace("http://www.w3.org/ns/sosa/")
        self.oboe = self.orka.get_namespace("http://ecoinformatics.org/oboe/oboe.1.2/oboe-core.owl#")
        self.ssn = self.orka.get_namespace("http://www.w3.org/ns/ssn/")

        # Subscribe to the appropriate image topic
        rospy.Subscriber(self.camera_topic, Image, self.image_callback)
        rospy.loginfo("MainAnnotatorClient initialized.")

    def load_config(self):
        """Load main configuration and determine service parameters."""
        # Use rospkg to get the path of the "orvis" package
        rospack = rospkg.RosPack()
        package_path = rospack.get_path('orvis')
        main_config_path = f"{package_path}/config/orvis_config.yaml"

        # Load the main config file
        with open(main_config_path, 'r') as file:
            self.config = yaml.safe_load(file)

        # Determine service to test (can be adjusted to allow dynamic selection)
        # self.service_name = self.config['system']['service_to_test']
        # self.task_type = self.service_name.split('/')[2]

        # if self.task_type == 'ImageSegmentation':
        #     self.service_type = ImageSegmentation 
        # elif self.task_type == 'ObjectDetection':
        #     self.service_type = ObjectDetection
        # elif self.task_type == 'PromptedObjectDetection':
        #     self.service_type = PromptedObjectDetection
        # elif self.task_type == 'DepthEstimation':
        #     self.service_type = DepthEstimation
        # elif self.task_type == 'VideoClassification':
        #     self.service_type = VideoClassification
        # elif self.task_type == 'ImageToText':
        #     self.service_type = ImageToText
        # else:
        #     raise NameError("Service type not recognized. Check the name of the services.")
        # Determine the camera topic
        self.camera_topic = self.config['system']['camera_topic']
        # Determine ORKA path
        self.orka_path = self.config['system']['orka_path']
        # Determine the number of frames to collect for a video
        self.num_frames = self.config['system']['num_video_frames']
        # Determine logging level
        self.logging_level = self.config['system']['logging_level']

    def image_callback(self, img_msg):
        """Store the last received image."""
        self.last_image = img_msg

    def call_service(self, service_to_call):
        """
        Call the specified service using the last received image.

        :param service_to_call: A string representing the service to call
                                (e.g., 'ObjectDetection', 'ImageSegmentation', etc.).
        """
        # Wait until at least one image is received
        while not rospy.is_shutdown() and self.last_image is None:
            rospy.loginfo("Waiting for an image...")
            rospy.sleep(0.1)  # Sleep for a short duration to avoid busy-waiting

        
        task_type = service_to_call.split('/')[2]


        if task_type == 'ImageSegmentation':
            self.service_type = ImageSegmentation 
        elif task_type == 'ObjectDetection':
            self.service_type = ObjectDetection
        elif task_type == 'PromptedObjectDetection':
            self.service_type = PromptedObjectDetection
        elif task_type == 'DepthEstimation':
            self.service_type = DepthEstimation
        elif task_type == 'VideoClassification':
            self.service_type = VideoClassification
        elif task_type == 'ImageToText':
            self.service_type = ImageToText
        else:
            raise NameError("Service type not recognized. Check the name of the services.")


        rospy.wait_for_service(service_to_call)
        self.annotator_service = rospy.ServiceProxy(service_to_call, self.service_type)
        rospy.loginfo(f"Service {service_to_call} connected.")

        try:
            # Dispatch the request to the appropriate service processing method
            if task_type == 'ObjectDetection':
                self.process_detection(self.last_image)
            elif task_type == 'PromptedObjectDetection':
                self.process_prompteddetection(self.last_image)
            elif task_type == 'ImageSegmentation':
                self.process_segmentation(self.last_image)
            elif task_type == 'DepthEstimation':
                self.process_depthestimation(self.last_image)
            elif task_type == 'VideoClassification':
                self.process_videoclassification(self.last_image)
            elif task_type == 'ImageToText':
                self.process_image_to_text(self.last_image)
            else:
                rospy.logerr(f"Unknown service type: {service_to_call}. Cannot process the request.")
        except Exception as e:
            rospy.logerr(f"Error calling service {service_to_call}: {e}")

    # def image_callback(self, img_msg):
    #     """Callback for the image topic."""
    #     current_time = rospy.Time.now()
    #     if (current_time - self.last_request_time) < self.request_interval:
    #         return  # Skip if the time interval hasn't passed

    #     # Update the last request time
    #     self.last_request_time = current_time

    #     # Send the image to the appropriate service
    #     if self.service_type == ObjectDetection:
    #         self.process_detection(img_msg)
    #     elif self.service_type == PromptedObjectDetection:
    #         self.process_prompteddetection(img_msg)
    #     elif self.service_type == ImageSegmentation:
    #         self.process_segmentation(img_msg)
    #     elif self.service_type == DepthEstimation:
    #         self.process_depthestimation(img_msg)
    #     elif self.service_type == VideoClassification:
    #         self.process_videoclassification(img_msg)
    #     elif self.service_type == ImageToText:
    #         self.process_image_to_text(img_msg)

    def create_obs_graph(self, result):
        """
        Creates an observation graph
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        observation_id = 'obs_' + timestamp  # Format: YYYYMMDDHHMMSS
        obs_instance = self.oboe.Observation(observation_id) # Create an instance of Observation
        # TODO: Add UsedProcedure Procedure

        if self.service_type == ObjectDetection or self.service_type == PromptedObjectDetection or self.service_type == ImageToText:
            for boundingbox in result.objects.bounding_boxes:
                rospy.loginfo(f'Creating observation for {boundingbox.Class}')
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))

                # Creating instances
                try:
                    ent_instance = self.orka[boundingbox.Class.capitalize()]('ent_' + timestamp)
                except Exception as e:
                    rospy.loginfo(f"Class \"{boundingbox.Class.capitalize()}\" not found. Defaulting to PhysicalEntity")
                    ent_instance = self.orka['PhysicalEntity']('ent_' + timestamp)
                char_instance = self.orka.Location('loc_' + timestamp)
                mes_instance = self.oboe.Measurement('mes_' + timestamp)
                result_instance = self.sosa.Result('res_' + timestamp)

                # Adding properties
                obs_instance.hasMeasurement.append(mes_instance)
                mes_instance.hasResult.append(result_instance)
                mes_instance.ofCharacteristic = char_instance
                char_instance.characteristicFor = ent_instance
                obs_instance.ofEntity = ent_instance

                # Adding data properties
                result_instance.hasValue.append(str(boundingbox))
                result_instance.hasProbability.append(boundingbox.probability)
                char_instance.hasValue.append("{}, {}".format(int((boundingbox.xmin + boundingbox.xmax)/2), int((boundingbox.ymin + boundingbox.ymax)/2)))

        elif self.service_type == ImageSegmentation:
            for imagemask in result.objects.masks:
                rospy.loginfo(f'Creating observation for {imagemask.Class}')
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))

                # Creating instances
                try:
                    ent_instance = self.orka[imagemask.Class.capitalize()]('ent_' + timestamp)
                except Exception as e:
                    rospy.loginfo(f"Class \"{imagemask.Class.capitalize()}\" not found. Defaulting to PhysicalEntity")
                    ent_instance = self.orka['PhysicalEntity']('ent_' + timestamp)
                char_instance = self.orka.Location('loc_' + timestamp)
                mes_instance = self.oboe.Measurement('mes_' + timestamp)
                result_instance = self.sosa.Result('res_' + timestamp)

                # Adding properties
                obs_instance.hasMeasurement.append(mes_instance)
                mes_instance.hasResult.append(result_instance)
                mes_instance.ofCharacteristic = char_instance
                char_instance.characteristicFor = ent_instance
                obs_instance.ofEntity = ent_instance

                # Adding data properties
                result_instance.hasValue.append(str(imagemask))
                result_instance.hasProbability.append(imagemask.probability)
                # TODO: Need to calculate middle of the mask
                # char_instance.hasValue.append("{}, {}".format(int((imagemask.xmin + imagemask.xmax)/2), int((imagemask.ymin + imagemask.ymax)/2)))

        elif self.service_type == DepthEstimation:
            rospy.loginfo(f'Creating observation for Depth Map')
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

            depth_map = result.depth_map.data
            # Creating instances
            ent_instance = self.orka['PhysicalEntity']('ent_' + timestamp)
            char_instance = self.orka.Location('loc_' + timestamp)
            mes_instance = self.oboe.Measurement('mes_' + timestamp)
            result_instance = self.sosa.Result('res_' + timestamp)

            # Adding properties
            obs_instance.hasMeasurement.append(mes_instance)
            mes_instance.hasResult.append(result_instance)
            mes_instance.ofCharacteristic = char_instance
            char_instance.characteristicFor = ent_instance
            obs_instance.ofEntity = ent_instance

            # Adding data properties
            result_instance.hasValue.append(depth_map)
            char_instance.hasValue.append(depth_map)
            
        elif self.service_type == VideoClassification:
            rospy.loginfo(f'Creating observation for {result.activity}')
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

            # Creating instances
            ent_instance = self.orka['PhysicalEntity']('ent_' + timestamp)
            char_instance = self.orka.ActivityType('activity_' + timestamp)
            mes_instance = self.oboe.Measurement('mes_' + timestamp)
            result_instance = self.sosa.Result('res_' + timestamp)

            # Adding properties
            obs_instance.hasMeasurement.append(mes_instance)
            mes_instance.hasResult.append(result_instance)
            mes_instance.ofCharacteristic = char_instance
            char_instance.characteristicFor = ent_instance
            obs_instance.ofEntity = ent_instance

            # Adding data properties
            result_instance.hasValue.append(str(result.activity.data))
            char_instance.hasValue.append(str(result.activity.data))

        self.orka.save(self.save_dir)

    def process_prompteddetection(self, img_msg):
        """Process image detection service requests."""
        try:
            # Convert the ROS Image message to OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(img_msg, "bgr8")
            request = PromptedObjectDetectionRequest(image=img_msg, prompt=self.prompt)
            response = self.annotator_service(request)

            # If logging level is DEBUG, display the bounding boxes
            if self.logging_level == 'DEBUG':
                self.display_bounding_boxes(cv_image, response)
            self.create_obs_graph(response)
            return response

        except Exception as e:
            rospy.logerr(f"Error processing detection image: {e}")

    def process_image_to_text(self, img_msg):
        """Process image detection service requests."""
        try:
            # Convert the ROS Image message to OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(img_msg, "bgr8")
            request = ImageToTextRequest(image=img_msg)
            response = self.annotator_service(request)

            # If logging level is DEBUG, display the bounding boxes
            if self.logging_level == 'DEBUG':
                self.display_bounding_boxes(cv_image, response)
            self.create_obs_graph(response)
            return response
        except Exception as e:
            rospy.logerr(f"Error processing detection image: {e}")

    def process_detection(self, img_msg):
        """Process image detection service requests."""
        try:
            # Convert the ROS Image message to OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(img_msg, "bgr8")
            request = ObjectDetectionRequest(image=img_msg)
            response = self.annotator_service(request)

            # If logging level is DEBUG, display the bounding boxes
            if self.logging_level == 'DEBUG':
                self.display_bounding_boxes(cv_image, response)

            self.create_obs_graph(response)
            return response
        
        except Exception as e:
            rospy.logerr(f"Error processing detection image: {e}")

    def process_segmentation(self, img_msg):
        """Process segmentation service requests."""
        try:
            # Convert the ROS Image message to OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(img_msg, "bgr8")
            request = ImageSegmentationRequest(image=img_msg)
            response = self.annotator_service(request)

            # If logging level is DEBUG, display the segmentation masks
            if self.logging_level == 'DEBUG':
                self.display_segmentation_masks(cv_image, response)
            self.create_obs_graph(response)
            return response
        
        except Exception as e:
            rospy.logerr(f"Error processing segmentation image: {e}")

    def process_depthestimation(self, img_msg):
        """Process depth estimation service requests."""
        try:
            # Convert the ROS Image message to OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(img_msg, "bgr8")
            request = DepthEstimationRequest(image=img_msg)
            response = self.annotator_service(request)

            # If logging level is DEBUG, display the bounding boxes
            if self.logging_level == 'DEBUG':
                self.display_depthmap(response)
            self.create_obs_graph(response)
            return response
        except Exception as e:
            rospy.logerr(f"Error processing detection image: {e}")

    def process_videoclassification(self, img_msg):
        """Process depth estimation service requests."""
        try:
            # Convert the ROS Image message to OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(img_msg, "bgr8")
            self.video_frames.append(cv_image)
            if len(self.video_frames) == self.num_frames:
                ros_video_frames = [self.bridge.cv2_to_imgmsg(frame, "bgr8") for frame in self.video_frames]

                request = VideoClassificationRequest(video_frames=ros_video_frames)
                response = self.annotator_service(request)
                rospy.loginfo(f"Detected activity: {response}")
                self.create_obs_graph(response)
                return response
            
            else:
                rospy.loginfo(f"Collecting frames ({len(self.video_frames)}/{self.num_frames} frames collected)")
        except Exception as e:
            rospy.logerr(f"Error processing detection image: {e}")

# DISPLAY FUNCTIONS

    def display_bounding_boxes(self, image, response):
        """Display bounding boxes from the detection response."""
        for bbox in response.objects.bounding_boxes:
            x_min, y_min, x_max, y_max = int(bbox.xmin), int(bbox.ymin), int(bbox.xmax), int(bbox.ymax)
            cv2.rectangle(image, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
            cv2.putText(image, f"{bbox.Class} ({round(bbox.probability, 2)})", (x_min, y_min - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        # Display the image
        cv2.imshow('Annotated Image', image)
        cv2.waitKey(1)

    def display_segmentation_masks(self, image, response):
        """Display segmentation masks from the segmentation response."""
        for mask in response.objects.masks:
            # Convert the mask to OpenCV format (mono8)
            mask_image = self.bridge.imgmsg_to_cv2(mask.mask, "mono8")

            # Overlay the mask on the image
            colored_mask = cv2.applyColorMap(mask_image, cv2.COLORMAP_JET)
            overlaid_image = cv2.addWeighted(image, 0.7, colored_mask, 0.3, 0)

            # Find the top-most pixel in the mask for the label
            mask_indices = cv2.findNonZero(mask_image)
            if mask_indices is not None:
                top_left = tuple(mask_indices.min(axis=0)[0])
                text_position = (top_left[0], max(10, top_left[1] - 10))
                cv2.putText(overlaid_image, f"{mask.Class} ({round(mask.probability, 2)})", text_position,
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            # Display the mask
            cv2.imshow('Segmentation Image', overlaid_image)
            cv2.waitKey(1)

    def display_depthmap(self, response):
        """
        Display the depth map from a DepthEstimationResponse.

        Args:
            response (DepthEstimationResponse): The response containing the depth map.

        Returns:
            None
        """
        try:
            # Extract metadata
            width = response.depth_map.width
            height = response.depth_map.height

            # Decode raw byte data if necessary
            if isinstance(response.depth_map.data, bytes):
                depth_data = np.frombuffer(response.depth_map.data, dtype=np.uint8).astype(np.float32)
            else:
                depth_data = np.array(response.depth_map.data, dtype=np.float32)

            # Check if reshaping is possible
            if depth_data.size != width * height:
                rospy.logerr(
                    f"Mismatch in depth data size ({depth_data.size}) and dimensions ({width}x{height})"
                )
                return

            # Reshape to original dimensions
            depth_data = depth_data.reshape((height, width))

            # Normalize depth values for visualization
            max_value = depth_data.max()
            if max_value <= 0:
                rospy.logerr("Invalid max value in depth data. Cannot normalize.")
                return

            formatted_depth = (depth_data * 255 / max_value).astype("uint8")

            # Display the depth map
            cv2.imshow("Depth Estimation", formatted_depth)
            rospy.loginfo("Press any key in the display window to exit.")
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        except Exception as e:
            rospy.logerr(f"Failed to display depth map: {e}")


def query_annotators(obs_graph, object):
    """
    Queries the observation graph for annotators able to detect the given object using a SPARQL query.
    Adds a simulated entity of the given type to the ontology, performs reasoning, and then executes the query.
    
    :param obs_graph: The loaded ontology graph (owlready2 ontology object).
    :param object: The target object (assumed to be an IRI or identifier).
    :return: List of results from the SPARQL query, or None if no results are found.
    """
    try:
        rospy.loginfo(f"Adding a simulated entity of type {object} to the ontology...")
        
        # Step 1: Add a simulated entity of type 'object' to the ontology
        with obs_graph:
            simulated_entity = obs_graph[object](f"SimulatedEntity_{object}")
            # simulated_entity.is_a.append()  # Assign type `object`
            rospy.loginfo("Running reasoning...")
            sync_reasoner_pellet(infer_property_values=True, debug=0)
            rospy.loginfo("Reasoning complete.")

        # Step 2: Construct and run the SPARQL query
        rospy.loginfo(f"Querying the observation graph for annotators capable of detecting {object}...")
        sparql_query_annotators = f"""
        PREFIX sosa: <http://www.w3.org/ns/sosa/>
        PREFIX ssn: <http://www.w3.org/ns/ssn/>
        PREFIX orka: <https://w3id.org/def/orka#>
        PREFIX oboe: <http://ecoinformatics.org/oboe/oboe.1.2/oboe-core.owl#>

        SELECT DISTINCT ?annotator
        WHERE {{
          # Query for the simulated entity and related annotators
          ?temp_entity a orka:{object} .
          ?annotator orka:canDetect ?temp_entity .
        }}
        """
        results = list(default_world.sparql(sparql_query_annotators, error_on_undefined_entities=False))
        rospy.loginfo(f"SPARQL query returned {len(results)} results.")
        print(results)
        return results if results else None
    
    except Exception as e:
        rospy.logerr(f"Error running query_annotators function: {e}")
        return None

def get_obs_graph():
    """
    Fetches and loads the most recently modified observation graph (.owl file) 
    from the knowledge base directory using owlready2.
    Returns the loaded ontology or None if no .owl file exists.
    """
    rospy.loginfo("Fetching observation graph...")

    # Path to the obs_graphs directory (one level up from the script directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    obs_graph_dir = os.path.join(os.path.dirname(script_dir), "obs_graphs")

    # Check if the directory exists
    if not os.path.exists(obs_graph_dir):
        rospy.logwarn(f"The directory {obs_graph_dir} does not exist.")
        return None

    # Get all .owl files in the directory
    owl_files = [os.path.join(obs_graph_dir, f) for f in os.listdir(obs_graph_dir) if f.endswith(".owl")]

    # If no .owl files are found, return None
    if not owl_files:
        rospy.logwarn(f"No .owl files found in {obs_graph_dir}.")
        return None

    # Find the most recently modified .owl file
    latest_obs_graph_path = max(owl_files, key=os.path.getmtime)
    rospy.loginfo(f"Latest observation graph found: {latest_obs_graph_path}")

    # Load the ontology using owlready2
    try:
        ontology = get_ontology(latest_obs_graph_path).load()
        rospy.loginfo(f"Ontology successfully loaded from {latest_obs_graph_path}.")
        return ontology
    except Exception as e:
        rospy.logerr(f"Failed to load ontology: {e}")
        return None

def create_obs_graph():
    """
    Creates a new observation graph.
    Returns the newly created observation graph.
    """
    rospy.loginfo("Creating a new observation graph...")
    return {"graph": "new_obs_graph"}


def query_location(obs_graph, object):
    """
    Queries the observation graph for the location of the given object using a SPARQL query.
    :param obs_graph: The loaded ontology graph (owlready2 ontology object).
    :param object: The target object (assumed to be an IRI or identifier).
    :return: List of results from the SPARQL query, or None if no results are found.
    """
    rospy.loginfo(f"Querying the observation graph for the location of {object}...")

    sparql_query_location = f"""
    PREFIX sosa: <http://www.w3.org/ns/sosa/>
    PREFIX ssn: <http://www.w3.org/ns/ssn/>
    PREFIX orka: <https://w3id.org/def/orka#>
    PREFIX oboe: <http://ecoinformatics.org/oboe/oboe.1.2/oboe-core.owl#>

    SELECT ?loc ?ent WHERE {{
      ?ent a orka:{object} .
      ?loc_instance a orka:Location .
      ?loc_instance oboe:characteristicFor ?ent .
      ?loc_instance orka:hasValue ?loc .                               
    }}
    """

    try:
        # Run the SPARQL query on the ontology
        results = list(default_world.sparql(sparql_query_location, error_on_undefined_entities=False))
        rospy.loginfo(f"SPARQL query returned {len(results)} results.")
        return results if results else None
    except Exception as e:
        rospy.logerr(f"Error running SPARQL query: {e}")
        return None

def call_annotator(annotator, object):
    """
    Calls the annotator service to detect the given object.
    """
    rospy.loginfo(f"Calling annotator service '{annotator}' to detect {object}...")
    try:
        rospy.wait_for_service(annotator, timeout=5.0)
        annotator_service = rospy.ServiceProxy(annotator, AnnotatorService)
        request = AnnotatorServiceRequest()
        request.object = object  # Populate request fields as required
        response = annotator_service(request)
        rospy.loginfo(f"Annotator service '{annotator}' response: {response}")
    except rospy.ServiceException as e:
        rospy.logerr(f"Failed to call annotator service '{annotator}': {e}")


def pickup_object(object_position):
    """
    Sends a goal to the pickup action server to pick up an object at the given position.
    """
    rospy.loginfo(f"Sending goal to pickup action for position {object_position}...")

    # Create an action client for the pickup action
    client = actionlib.SimpleActionClient('/pickup_action', PickupAction)

    # Wait for the action server to be available
    rospy.loginfo("Waiting for pickup action server...")
    client.wait_for_server()

    # Create and send the goal
    goal = PickupGoal()
    goal.position.x = object_position["x"]
    goal.position.y = object_position["y"]

    rospy.loginfo(f"Sending pickup goal: {goal}")
    client.send_goal(goal)

    # Wait for the result
    client.wait_for_result()
    result = client.get_result()

    rospy.loginfo(f"Pickup action completed with result: {result}")


# # Main script
# if __name__ == "__main__":
#     rospy.init_node("object_locator_node")

#     #fruit_salad_items = ['Banana', 'Apple', 'Strawberry', 'Orange', 'Pineapple']
#     fruit_salad_items = ['Banana']


#     for fruit in fruit_salad_items:
#         rospy.loginfo(f"Processing {fruit}...")
#         fruit_position = None

#         obs_graph = get_obs_graph()
#         if not obs_graph:
#             obs_graph = create_obs_graph()

#         options_left = True

#         fruit_position = query_location(obs_graph, fruit)
#         while options_left and not fruit_position:
#             capable_annotators = query_annotators(obs_graph, fruit)
#             for annotator in capable_annotators:
#                 call_annotator(annotator, fruit)
#                 obs_graph = get_obs_graph()
#                 fruit_position = query_location(obs_graph, fruit)

#                 if fruit_position:
#                     break

#                 capable_annotators.remove(annotator)
#                 if not capable_annotators:
#                     options_left = False

#         if fruit_position:
#             pickup_object(fruit_position)
#         else:
#             rospy.loginfo(f"{fruit} not found!")

if __name__ == "__main__":
    try:
        annotator_client = TaskSelector()
        annotator_client.call_service('/annotators/ObjectDetection/yolos_tiny/detect')
        annotator_client.call_service('/annotators/ImageSegmentation/detr_resnet_50_panoptic/detect')
        rospy.spin()
    except rospy.ROSInterruptException:
        pass