import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
from torch.utils.data import DataLoader

# Load the dataset
transform = transforms.Compose([transforms.ToTensor()])
train_dataset = datasets.FashionMNIST(root='./data', train=True,download=True, transform=transform)
test_dataset = datasets.FashionMNIST(root='./data', train=False,download=True, transform=transform)
train_loader = DataLoader(train_dataset, batch_size=64,shuffle=True)
test_loader = DataLoader(test_dataset, batch_size=64,shuffle=False)
# Define the model
class FashionMNISTModel(nn.Module):
     def __init__(self):
         super(FashionMNISTModel, self).__init__()
         self.flatten = nn.Flatten()
         self.linear_relu_stack = nn.Sequential(
             nn.Linear(28*28, 128),
             nn.ReLU(),
             nn.Linear(128, 10),
             nn.LogSoftmax(dim=1)
             )
     def forward(self, x):
         x = self.flatten(x)
         logits = self.linear_relu_stack(x)
         return logits

model = FashionMNISTModel()
    # Define the loss function and optimizer
loss_function = nn.NLLLoss()
optimizer = optim.Adam(model.parameters())

def get_accuracy(pred, labels):
    _, predictions = torch.max(pred, 1)
    correct = (predictions == labels).float().sum()
    accuracy = correct / labels.shape[0]
    return accuracy

    # Train the model
def train(dataloader, model, loss_fn, optimizer):
     size = len(dataloader.dataset)
     model.train()
     for batch, (X, y) in enumerate(dataloader):
         # Compute prediction and loss
         pred = model(X)
         loss = loss_fn(pred, y)
         accuracy = get_accuracy(pred, y)
         # Backpropagation
         optimizer.zero_grad()
         loss.backward()
         optimizer.step()
         if batch % 100 == 0:
            current = batch * len(X)
            avg_loss = loss / (batch + 1)
            avg_accuracy = accuracy / (batch + 1) * 100

            print(f"Batch {batch}, Loss: {avg_loss:>7f}, Accuracy: {avg_accuracy: > 0.2f} %[{current: > 5d} / {size: > 5d}]")
        # Training process
         if avg_accuracy >= 95:
             print("Reached 95% accuracy, stopping training.")
             return True  # Stop training


epochs = 50
for t in range(epochs):
    print(f"Epoch {t+1}\n-------------------------------")
    train(train_loader, model, loss_function, optimizer)
print("Done!")


import matplotlib.pyplot as plt
def predict_single_image(image, label, model):
    # Set the model to evaluation mode
    model.eval()
    # Unsqueeze image as the model expects a batch dimension
    image = image.unsqueeze(0)
    with torch.no_grad():
        prediction = model(image)
        print(prediction)
        predicted_label = prediction.argmax(1).item()
    # Display the image and predictions
    plt.imshow(image.squeeze(), cmap='gray')
    plt.title(f'Predicted: {predicted_label}, Actual: {label}')
    plt.show()
    return predicted_label
    # Choose an image from the test set
image, label = test_dataset[0]  # Change index to test different images
    # Predict the class for the chosen image
predicted_label = predict_single_image(image, label, model)
print(f"The model predicted {predicted_label}, and the actual label is {label}.")