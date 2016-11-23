# chaos_theory

Implementations of various RL algorithms using OpenAI Gym environments
- REINFORCE
- DDPG
- NAF

TODO:
- TRPO/Natural Policy Gradients
- QProp


Requirements
============

- Python 2.7
- OpenAI Gym (https://github.com/openai/gym)
- Tensorflow (https://github.com/tensorflow/tensorflow)
- Numpy/Scipy


Instructions
============

REINFORCE Cartpole experiment:
```
python scripts/run_reinforce.py
````

DDPG Half-Cheetah experiment:
```
python scripts/run_ddpg2.py
````
![alt text](https://github.com/justinjfu/resources/blob/master/rl_site/cheetah_ddpg.gif "Cheetah DDPG")
