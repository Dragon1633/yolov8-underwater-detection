import torch
print(torch.__version__)		# eg:2.2.2+cpu则表示为cpu版本，2.2.2+cu121则是有gpu
print(torch.version.cuda)
print(torch.cuda.is_available())  #输出为True，则安装无误