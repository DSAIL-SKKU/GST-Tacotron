import tensorflow as tf
from tensorflow.contrib.rnn import GRUCell


def prenet(inputs, is_training, layer_sizes, scope=None):
	"""
	Args:
		inputs: input vector
		is_training: dropout option
		layer_sizes: iteration number
	
	Output:
		x: prenet
	"""
	x = inputs
	drop_rate = 0.5 if is_training else 0.0 # set dropout rate 0.5 (only training)
	with tf.variable_scope(scope or 'prenet'):
		for i, size in enumerate(layer_sizes): # iterate layer_sizes
			dense = tf.layers.dense(x, units=size, activation=tf.nn.relu, name='dense_%d' % (i + 1))
			x = tf.layers.dropout(dense, rate=drop_rate, training=is_training, name='dropout_%d' % (i + 1)) 
	return x


def encoder_cbhg(inputs, input_lengths, is_training, depth):
	"""
	Args:
		inputs: input tensor
		input_lengths: length of input tensor
		is_training: Batch Normalization option in Conv1D
		depth: dimensionality option of Highway net and Bidirectical GRU's output
	
	Output:
		cbhg function
	"""
	input_channels = inputs.get_shape()[2] # 3rd element of inputs' shape
	return cbhg(
		inputs,
		input_lengths,
		is_training,
		scope='encoder_cbhg',
		K=16,
		projections=[128, input_channels],
		depth=depth)


def post_cbhg(inputs, input_dim, is_training, depth):
	"""
	Args:
		inputs: input tensor
		input_dim: dimension of input tensor
		is_training: Batch Normalization option in Conv1D
		depth: dimensionality option of Highway net and Bidirectical GRU's output
	
	Output:
		cbhg function
	"""
	return cbhg(
		inputs,
		None,
		is_training,
		scope='post_cbhg',
		K=8,
		projections=[256, input_dim],
		depth=depth)


def cbhg(inputs, input_lengths, is_training, scope, K, projections, depth):
    """
    Args:
        inputs: input tensor
        input_lengths: length of input tensor
        is_training: Batch Normalization option in Conv1D
        scope: network or model name
        K: kernel size range
        projections: projection layers option
        depth: dimensionality option of Highway net and Bidirectical GRU's output
    The layers in the code are staked in the order in which they came out.
    """
    with tf.variable_scope(scope):
        with tf.variable_scope('conv_bank'):

            conv_outputs = tf.concat(
                [conv1d(inputs, k, 128, tf.nn.relu, is_training, 'conv1d_%d' % k) for k in range(1, K + 1)], #1D Convolution layers using multiple types of Convolution Kernel.
                axis=-1																						 #Iterate K with increasing filter size by 1.
            )# Convolution bank: concatenate on the last axis to stack channels from all convolutions

        # Maxpooling:
        maxpool_output = tf.layers.max_pooling1d(
            conv_outputs,
            pool_size=2,
            strides=1,
            padding='same') #1D Maxpooling layer(strides=1, width=2) 

        # Two projection layers:
        proj1_output = conv1d(maxpool_output, 3, projections[0], tf.nn.relu, is_training, 'proj_1')#1st Conv1D projections
        proj2_output = conv1d(proj1_output, 3, projections[1], None, is_training, 'proj_2')#2nd Conv1D projections

        # Residual connection:
        highway_input = proj2_output + inputs #Highway net input with residual connection

        half_depth = depth // 2
        assert half_depth * 2 == depth, 'encoder and postnet depths must be even.' #assert depth to be even

        # Handle dimensionality mismatch:
        if highway_input.shape[2] != half_depth: #check input's dimensionality and output's dimensionality are the same
            highway_input = tf.layers.dense(highway_input, half_depth) #change input's channel size to Highway net output's  size

        # 4-layer HighwayNet:
        for i in range(4):
            highway_input = highwaynet(highway_input, 'highway_%d' % (i + 1), half_depth) #make 4 Highway net layers
        rnn_input = highway_input

        # Bidirectional GRU
        outputs, states = tf.nn.bidirectional_dynamic_rnn( #make Bidirectional GRU
            GRUCell(half_depth),
            GRUCell(half_depth),
            rnn_input,
            sequence_length=input_lengths,
            dtype=tf.float32)
        return tf.concat(outputs, axis=2)  # Concat forward sequence and backward sequence

def highwaynet(inputs, scope, depth):
	with tf.variable_scope(scope):
		H = tf.layers.dense(
			inputs,
			units=depth,
			activation=tf.nn.relu,
			name='H')
		T = tf.layers.dense(
			inputs,
			units=depth,
			activation=tf.nn.sigmoid,
			name='T',
			bias_initializer=tf.constant_initializer(-1.0))
		return H * T + inputs * (1.0 - T)


def conv1d(inputs, kernel_size, channels, activation, is_training, scope):
	"""
	Args:
		inputs: input tensor
		kernel_size: length of the 1D convolution window
		channels: dimensionality of the output space
		activation: Activation function (None means linear activation)
		is_training: Batch Normalization option in Conv1D
		scope: namespace
	
	Output:
		output tensor
	"""
	with tf.variable_scope(scope):
		conv1d_output = tf.layers.conv1d( # creates a convolution kernel
			inputs,
			filters=channels,
			kernel_size=kernel_size,
			activation=activation,
			padding='same') # return output tensor
		return tf.layers.batch_normalization(conv1d_output, training=is_training)
