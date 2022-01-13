#Copyright (c) Facebook, Inc. and its affiliates.
#All rights reserved.

#This source code is licensed under the license found in the
#LICENSE file in the root directory of this source tree.

import torch.nn as nn
import torch
import numpy as np
from torch.nn.parameter import Parameter
import torch.nn.functional as F
import math
from ..utils import load_mesh_vision, ARGS, chamfer_distance_mesh2pc

from rfvision.models.human_analyzers import BasePose
from rfvision.models.builder import DETECTORS

# network for making image features for vertex feature vectors
class Image_Encoder(nn.Module):
	def __init__(self, args):
		super(Image_Encoder, self).__init__()
		layers = []
		cur_size = 6
		next_size = 16

		for i in range(args.num_img_blocks):
			layers.append(CNN_layer(cur_size, next_size, args.size_img_ker, stride=2))
			cur_size = next_size
			next_size = next_size * 2
			for j in range(args.num_img_layers -1):
				layers.append(CNN_layer(cur_size, cur_size, args.size_img_ker))

		self.args = args
		self.layers = nn.ModuleList(layers)
		f = 221.7025
		RT = np.array([[-0.0000, -1.0000, 0.0000, -0.0000],
					   [-0.7071, 0.0000, -0.7071, 0.4243],
					   [0.7071, 0.0000, -0.7071, 1.1314]])
		K = np.array([[f, 0, 128.], [0, f, 128.], [0, 0, 1]])
		self.matrix = torch.FloatTensor(K.dot(RT)).cuda()

	# implemented from:
	# https://github.com/EdwardSmith1884/GEOMetrics/blob/master/utils.py
	# MIT License
	# defines image features over vertices from vertex positions, and feature mpas from vision
	def pooling(self, blocks, verts_pos, debug=False):
		# convert vertex positions to x,y coordinates in the image, scaled to fractions of image dimension
		ext_verts_pos = torch.cat(
			(verts_pos, torch.FloatTensor(np.ones([verts_pos.shape[0], verts_pos.shape[1], 1])).cuda()), dim=-1)
		ext_verts_pos = torch.matmul(ext_verts_pos, self.matrix.permute(1, 0))
		xs = ext_verts_pos[:, :, 1] / ext_verts_pos[:, :, 2] / 256.
		ys = ext_verts_pos[:, :, 0] / ext_verts_pos[:, :, 2] / 256.

		full_features = None
		batch_size = verts_pos.shape[0]

		# check camera project covers the image
		if debug:
			dim = 256
			xs = (torch.clamp(xs * dim, 0, dim - 1).data.cpu().numpy()).astype(np.uint8)
			ys = (torch.clamp(ys * dim, 0, dim - 1).data.cpu().numpy()).astype(np.uint8)
			for ex in range(blocks.shape[0]):
				img = blocks[ex].permute(1, 2, 0).data.cpu().numpy()[:, :, :3]
				for x, y in zip(xs[ex], ys[ex]):
					img[x, y, 0] = 1
					img[x, y, 1] = 0
					img[x, y, 2] = 0

				from PIL import Image
				Image.fromarray((img * 255).astype(np.uint8)).save('results/temp.png')
				print('saved')
				input()



		for block in blocks:
			# scale projected vertex points to dimension of current feature map
			dim = block.shape[-1]
			cur_xs = torch.clamp(xs * dim, 0, dim - 1)
			cur_ys = torch.clamp(ys * dim, 0, dim - 1)


			# https://en.wikipedia.org/wiki/Bilinear_interpolation
			x1s, y1s, x2s, y2s = torch.floor(cur_xs), torch.floor(cur_ys), torch.ceil(cur_xs), torch.ceil(cur_ys)
			A = x2s - cur_xs
			B = cur_xs - x1s
			G = y2s - cur_ys
			H = cur_ys - y1s

			x1s = x1s.type(torch.cuda.LongTensor)
			y1s = y1s.type(torch.cuda.LongTensor)
			x2s = x2s.type(torch.cuda.LongTensor)
			y2s = y2s.type(torch.cuda.LongTensor)

			# flatten batch of feature maps to make vectorization easier
			flat_block = block.permute(1, 0, 2, 3).contiguous().view(block.shape[1], -1)
			block_idx = torch.arange(0, verts_pos.shape[0]).cuda().unsqueeze(-1).expand(batch_size, verts_pos.shape[1])
			block_idx = block_idx * dim * dim


			selection = (block_idx + (x1s * dim) + y1s).view(-1)
			C = torch.index_select(flat_block, 1, selection)
			C = C.view(-1, batch_size, verts_pos.shape[1]).permute(1, 0, 2)
			selection = (block_idx + (x1s * dim) + y2s).view(-1)
			D = torch.index_select(flat_block, 1, selection)
			D = D.view(-1, batch_size, verts_pos.shape[1]).permute(1, 0, 2)
			selection = (block_idx + (x2s * dim) + y1s).view(-1)
			E = torch.index_select(flat_block, 1, selection)
			E = E.view(-1, batch_size, verts_pos.shape[1]).permute(1, 0, 2)
			selection = (block_idx + (x2s * dim) + y2s).view(-1)
			F = torch.index_select(flat_block, 1, selection)
			F = F.view(-1, batch_size, verts_pos.shape[1]).permute(1, 0, 2)

			section1 = A.unsqueeze(1) * C * G.unsqueeze(1)
			section2 = H.unsqueeze(1) * D * A.unsqueeze(1)
			section3 = G.unsqueeze(1) * E * B.unsqueeze(1)
			section4 = B.unsqueeze(1) * F * H.unsqueeze(1)

			features = (section1 + section2 + section3 + section4)
			features = features.permute(0, 2, 1)

			if full_features is None:
				full_features = features
			else:
				full_features = torch.cat((full_features, features), dim=2)

		return full_features

	def forward(self, img_occ, img_unocc,  cur_vertices):
		# double size due to legacy decision
		if self.args.use_unoccluded:
			x = torch.cat((img_unocc, img_unocc), dim = 1)
		elif self.args.use_occluded:
			x = torch.cat((img_occ, img_occ), dim=1)
		else:
			x = torch.cat((img_occ, img_unocc), dim=1)

		features = []
		layer_selections = [len(self.layers) - 1 -  (i+1)*self.args.num_img_layers for i in range(3)]
		for e, layer in enumerate(self.layers):
			if x.shape[-1] < self.args.size_img_ker:
				break
			x = layer(x)
			# collect feature maps
			if e in layer_selections:
				features.append(x)
		features.append(x)
		# get vertex features from selected feature maps
		vert_image_features = self.pooling(features, cur_vertices)
		return vert_image_features




# global chart deformation class
@DETECTORS.register_module()
class VisionEncoder(BasePose):
	def __init__(self,
				 anno_root,
				 mode='no',
				 num_samples=10000,
				 GEOmetrics=False,
				 train_cfg=None,
				 test_cfg=None
				 ):
		super(VisionEncoder, self).__init__()

		# tycoer
		assert mode in ['no', 'empty', 'touch', 'touch_unoccluded', 'touch_occluded', 'unoccluded', 'occluded']
		self.args = ARGS(mode=mode)
		if GEOmetrics:
			self.adj_info, self.initial_positions = load_mesh_vision(self.args, f'{anno_root}/sphere.obj')
		else:
			self.adj_info, self.initial_positions = load_mesh_vision(self.args, f'{anno_root}/vision_sheets.obj')

		input_size = 3 # used to determine the size of the vertex feature vector
		if self.args.use_occluded or self.args.use_unoccluded:
			self.img_encoder = Image_Encoder(self.args).cuda()
			with torch.no_grad():
				input_size += self.img_encoder(torch.zeros(1, 3, 256, 256).cuda(), torch.zeros(1, 3, 256, 256).cuda(), torch.zeros(1, 1, 3).cuda()).shape[-1]
		if self.args.use_touch:
			input_size+=1

		self.mesh_decoder = GCN(input_size, self.args).cuda()
		self.loss_coeff = 9000
		self.num_samples = num_samples

	def get_pred(self, img_occ, img_unocc, **kwargs):
		# initial data
		batch_size = img_occ.shape[0]
		cur_vertices = self.initial_positions.unsqueeze(0).expand(batch_size, -1, -1)
		size_vision_charts = cur_vertices.shape[1]

		# if using touch then append touch chart position to graph definition
		if self.args.use_touch:
			sheets = kwargs['sheets']
			sheets = sheets.cuda().view(batch_size, -1, 3)
			cur_vertices = torch.cat((cur_vertices,sheets), dim = 1 )

		# cycle thorugh deformation
		for _ in range(3):
			vertex_features = cur_vertices.clone()
			# add vision features
			if self.args.use_occluded or self.args.use_unoccluded:
				vert_img_features = self.img_encoder(img_occ, img_unocc, cur_vertices)
				vertex_features = torch.cat((vert_img_features, vertex_features), dim=-1)
			# add mask for touch charts
			if self.args.use_touch:
				successful = kwargs['successful']
				vision_chart_mask = torch.ones(batch_size, size_vision_charts, 1).cuda() * 2 # flag corresponding to vision
				touch_chart_mask = torch.FloatTensor(successful).cuda().unsqueeze(-1).expand(batch_size, 4 * self.args.num_grasps, 25)
				touch_chart_mask = touch_chart_mask.contiguous().view(batch_size, -1, 1)
				mask = torch.cat((vision_chart_mask, touch_chart_mask), dim=1)
				vertex_features = torch.cat((vertex_features,mask), dim = -1)

			# deform the vertex positions
			vertex_positions = self.mesh_decoder(vertex_features, self.adj_info)
			# avoid deforming the touch chart positions
			vertex_positions[:, size_vision_charts:] = 0
			cur_vertices = cur_vertices + vertex_positions

		return cur_vertices

	def forward_train(self,
					  img_occ,
					  img_unocc,
					  gt_points,
					  **kwargs):
		verts = self.get_pred(img_occ, img_unocc, **kwargs)
		loss_dis = chamfer_distance_mesh2pc(verts, self.adj_info['faces'], gt_points, num=self.num_samples)
		loss_dis = self.loss_coeff * loss_dis.mean()
		losses = {'loss_dis': loss_dis}
		return losses

	def forward_test(self,
					 img_occ,
					 img_unocc,
					 gt_points,
					 **kwargs
					 ):
		# The evaluation metric of '3D-Vision-and_Touch' is loss,
		# Therefore forward_test return loss.
		losses = self.forward_train(img_occ,
					  				img_unocc,
					  				gt_points,
					  				**kwargs)
		return losses

	def show_result(self):
		pass

	def init_weights(self):
		pass

	def forward(self, return_loss=True, **kwargs):
		if return_loss:
			return self.forward_train(**kwargs)
		else:
			return self.forward_test(**kwargs)
# implemented from:
# https://github.com/tkipf/pygcn/tree/master/pygcn
# MIT License
# Graph convolutional network for chart deformation
class GCN(nn.Module):
	def __init__(self, input_features, args):
		super(GCN, self).__init__()

		self.num_layers = args.num_gcn_layers
		# define output sizes for each GCN layer
		hidden_values =  [input_features] + [ args.hidden_gcn_layers for k in range(self.num_layers -1)] + [3]

		# define layers
		layers = []
		for i in range(self.num_layers):
			layers.append(GCN_layer(hidden_values[i], hidden_values[i+1]))
		self.layers = nn.ModuleList(layers)


	def forward(self, vertex_features, adj_info):

		adj = adj_info['adj']
		# iterate through GCN layers
		x = self.layers[0](vertex_features, adj, F.relu)
		for i in range(1, self.num_layers-1):
			x = self.layers[i](x, adj, F.relu)
		coords = (self.layers[-1](x, adj, lambda x: x))

		return coords

# CNN layer definition
def CNN_layer(f_in, f_out, k, stride = 1):
	layers = []
	layers.append(nn.Conv2d(int(f_in), int(f_out), kernel_size=k, padding=1, stride=stride))
	layers.append(nn.BatchNorm2d(int(f_out)))
	layers.append(nn.ReLU(inplace=True))
	return  nn.Sequential(*layers)


# implemented from:
# https://github.com/tkipf/pygcn/tree/master/pygcn
# MIT License
# Graph convolutional network layer definition
class GCN_layer(nn.Module):
	def __init__(self, in_features, out_features, bias=True):
		super(GCN_layer, self).__init__()
		self.weight1 = Parameter(torch.Tensor(1, in_features, out_features))
		self.bias = Parameter(torch.Tensor(out_features))
		self.reset_parameters()

	def reset_parameters(self):
		stdv = 6. / math.sqrt((self.weight1.size(1) + self.weight1.size(0)))
		stdv *= .3
		self.weight1.data.uniform_(-stdv, stdv)
		self.bias.data.uniform_(-.1, .1)

	def forward(self, features, adj, activation):
		# 0N-GCN definition, removes need for resnet layers
		features = torch.matmul(features, self.weight1)
		output = torch.matmul(adj, features[:, :, :features.shape[-1] // 3])
		output = torch.cat((output, features[:, :, features.shape[-1] // 3:]), dim=-1)
		output = output + self.bias
		return activation(output)


