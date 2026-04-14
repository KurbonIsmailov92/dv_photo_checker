# Example

To test the system, you can use any 600x600 JPEG image.

For a quick test, you can create a sample image using Python:

```python
import cv2
import numpy as np

# Create a 600x600 white image
img = np.ones((600, 600, 3), dtype=np.uint8) * 255

# Add a simple face-like rectangle
cv2.rectangle(img, (200, 150), (400, 450), (100, 100, 100), -1)

cv2.imwrite('example/sample.jpg', img)
```

Then use it for testing.