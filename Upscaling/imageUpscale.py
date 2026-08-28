import os
import ssl
import urllib.request
import cv2

def download_model_if_missing(model_path):
    """Downloads the EDSR model weights if they do not exist locally."""
    if os.path.exists(model_path):
        print(f"Found local model weights: {model_path}")
        return

    # Ensure the directory exists before saving the model file
    os.makedirs(os.path.dirname(model_path), exist_ok=True)

    model_url = "https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/EDSR_x4.pb"
    
    print(f"Model weights not found at {model_path}.")
    print(f"Downloading EDSR x4 model from {model_url}...")
    
    try:
        # Create an unverified SSL context to bypass macOS certificate issues
        ssl_context = ssl._create_unverified_context()
        
        with urllib.request.urlopen(model_url, context=ssl_context) as response, open(model_path, 'wb') as out_file:
            out_file.write(response.read())
            
        print("Download complete successfully.")
    except Exception as e:
        print(f"Failed to download model automatically: {e}")
        print("Please check your internet connection or download the file manually.")

def enhance_border_image(input_image_path, model_path, output_image_path, scale=4):
    """
    Enhances a low-resolution security/surveillance image using the EDSR model.
    """
    if not os.path.exists(input_image_path):
        print(f"Error: Input image not found at {input_image_path}")
        return

    # Ensure model weights are present, downloading them automatically if missing
    download_model_if_missing(model_path)

    if not os.path.exists(model_path):
        print(f"Error: Model weights could not be found at {model_path}")
        return

    # Initialize the DNN super-resolution object
    sr = cv2.dnn_superres.DnnSuperResImpl_create()

    # Read the EDSR model
    print(f"Loading EDSR model from {model_path}...")
    sr.readModel(model_path)

    # Set the model algorithm and scaling factor
    sr.setModel("edsr", scale)

    # Read the low-resolution input image
    image = cv2.imread(input_image_path)

    print("Processing and enhancing image resolution...")
    # Execute the super-resolution upsampling
    result = sr.upsample(image)

    # Ensure output directory exists if specified with a path
    os.makedirs(os.path.dirname(output_image_path), exist_ok=True)

    # Save the enhanced output image
    cv2.imwrite(output_image_path, result)
    print(f"Enhanced image successfully saved to {output_image_path}")

if __name__ == "__main__":
    # Configuration paths matching your folder structure
    INPUT_IMAGE = "Upscaling/input/input.jpg"
    MODEL_WEIGHTS = "Upscaling/models/EDSR_x4.pb"
    OUTPUT_IMAGE = "Upscaling/output/upscaled.jpg"
    
    # Run the enhancement pipeline
    enhance_border_image(INPUT_IMAGE, MODEL_WEIGHTS, OUTPUT_IMAGE, scale=4)