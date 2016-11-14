import tempfile
import os
import pickle
import logging
from collections import deque, defaultdict

import tensorflow as tf
from abc import ABCMeta, abstractmethod

from chaos_theory.utils import BatchSampler

LOGGER = logging.getLogger(__name__)


def linear(input, dout=None, name=''):
    _, din = input.get_shape()
    W = tf.get_variable('W'+name, (din, dout))
    b = tf.get_variable('b'+name, (dout))
    return tf.matmul(input, W)+b


def grad_params(out, param_list):
    return [tf.gradients(out, param)[0] for param in param_list]


def assert_shape(tensor, shape):
    assert tensor.get_shape().is_compatible_with(shape), 'Shapes not compatible: %s vs %s' \
        % (tensor.get_shape(), shape)


class TFNet(object):
    __metaclass__ = ABCMeta

    def __init__(self, **build_args):
        self.__graph = tf.Graph()
        with self.__graph.as_default():
            self.build_network(**build_args)
        self.__init_network()

    @abstractmethod
    def build_network(self, **kwargs):
        raise NotImplementedError()

    def __init_network(self):
        self.__sess = tf.Session(graph=self.__graph)
        with self.__graph.as_default():
            self.saver = tf.train.Saver(tf.trainable_variables())
            self.__sess.run(tf.initialize_all_variables())

    def run(self, fetches, feed_dict=None):
        with self.__graph.as_default():
            results = self.__sess.run(fetches, feed_dict=feed_dict)
        return results

    def fit(self, dataset, heartbeat=100, max_iter=float('inf'), batch_size=10, lr=1e-3):
        sampler = BatchSampler(dataset)
        avg_loss = 0
        for i, batch in enumerate(sampler.with_replacement(batch_size=batch_size)):
            loss = self.train_step(batch, lr=lr)
            avg_loss += loss
            if i % heartbeat == 0 and i > 0:
                LOGGER.debug('Itr %d: Loss %f', i, avg_loss / heartbeat)
                avg_loss = 0
            if i > max_iter:
                break

    @abstractmethod
    def train_step(self, batch, lr):
        raise NotImplementedError()

    @property
    def sess(self):
        return self.__sess

    @property
    def graph(self):
        return self.__graph

    def __getstate__(self):
        return {'__wts': get_wt_string(self.saver, self.sess)}

    def __setstate__(self, state):
        restore_wt_string(self.saver, self.sess, state['__wts'])


def get_wt_string(saver, sess):
    with tempfile.NamedTemporaryFile('w+b', delete=True) as f:
        saver.save(sess, f.name)
        f.seek(0)
        with open(f.name, 'r') as f2:
            wts = f2.read()
        os.remove(f.name + '.meta')
    return wts

def restore_wt_string(saver, sess, wts):
    with tempfile.NamedTemporaryFile('w+b', delete=True) as f:
        f.write(wts)
        f.seek(0)
        saver.restore(sess, f.name)


def dump_pickle_str(obj):
    with tempfile.NamedTemporaryFile('w+b', delete=True) as f:
        pickle.dump(obj, f)
        f.seek(0)
        s = f.read()
    return s


def load_pickle_str(string):
    with tempfile.NamedTemporaryFile('w+b', delete=True) as f:
        f.write(string)
        f.seek(0)
        obj = pickle.load(f)
    return obj


class TFGraphDeps(object):
    def __init__(self, g=None):
        if g is None:
            self.g = tf.get_default_graph()
        else:
            self.g = g
        self.deps = self._calc_dependency_graph()

    def _calc_dependency_graph(self):
        """Build a dependency graph.

        Returns:
            a dict. Each key is the name of a node (Tensor or Operation) and each value is a set of
            dependencies (other node names)
        """
        deps = defaultdict(set)
        for op in self.g.get_operations():
            # the op depends on its input tensors
            for input_tensor in op.inputs:
                deps[op].add(input_tensor)
            # the op depends on the output tensors of its control_dependency ops
            for control_op in op.control_inputs:
                for output_tensor in control_op.outputs:
                    deps[op].add(output_tensor)
            # the op's output tensors depend on the op
            for output_tensor in op.outputs:
                deps[output_tensor].add(op)
        return deps

    def ancestors(self, op):
        """Get all nodes upstream of the current node."""
        explored = set()
        queue = deque([op])
        while len(queue) != 0:
            current = queue.popleft()
            for parent in self.deps[current]:
                if parent in explored: continue
                explored.add(parent)
                queue.append(parent)
        return explored


def _total_size(shape):
    tot = 1
    for dim in shape:
        tot = tot*int(dim)
    return tot


class ParamFlatten(object):
    def __init__(self, param_list):
        """
        :param param_list: A list of tensorflow variables
        """
        self.param_list = param_list
        self.shapes = [tensor.get_shape() for tensor in param_list]
        self.sizes = [_total_size(shape) for shape in self.shapes]
        self.total_size = sum(self.sizes)

    def pack(self, param_vals):
        vec = []
        for i, val in enumerate(param_vals):
            val = np.array(val)
            assert_shape(self.shapes[i], val.shape)
            flat = np.reshape(val, [-1])
            vec.append(flat)
        vec = np.concatenate(vec)
        return vec

    def unpack(self, param_vec):
        assert param_vec.shape == (self.total_size,)
        cur_idx = 0
        unflat = []
        for i, size in enumerate(self.sizes):
            param = param_vec[cur_idx:cur_idx+size]
            cur_idx += size
            unflat.append(np.reshape(param, self.shapes[i]))
        return unflat