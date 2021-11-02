import os
import sys
import wandb
import torch
import numpy as np
from icecream import ic
# Deal with relative import error
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from algorithms.utils.buffer import ReplayBuffer


def _t2n(x):
    return x.detach().cpu().numpy()

class Runner(object):
    def __init__(self, config):

        self.all_args = config['all_args']
        self.envs = config['envs']
        self.device = config['device']
        self.num_agents = config['num_agents']
        

        # parameters
        self.env_name = self.all_args.env_name
        self.algorithm_name = self.all_args.algorithm_name
        self.experiment_name = self.all_args.experiment_name
        self.num_env_steps = self.all_args.num_env_steps
        self.n_rollout_threads = self.all_args.n_rollout_threads
        self.buffer_size = self.all_args.buffer_size
        self.use_wandb = self.all_args.use_wandb

        # interval
        self.save_interval = self.all_args.save_interval
        self.log_interval = self.all_args.log_interval
        self.use_eval = self.all_args.use_eval
        self.eval_interval = self.all_args.eval_interval
        self.eval_episodes = self.all_args.eval_episodes

        # dir
        self.model_dir = self.all_args.model_dir
        self.run_dir = config["run_dir"]
        if self.use_wandb:
            self.save_dir = str(wandb.run.dir)
        else:
            self.save_dir = str(self.run_dir / 'models')
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)

        self.load()

    def load(self):
        # algorithm
        if self.algorithm_name == "ppo":
            from ..algorithms.ppo.ppo_trainer import PPOTrainer as Trainer
            from ..algorithms.ppo.ppo_policy import PPOPolicy as Policy
        else:
            raise NotImplementedError
        self.policy = Policy(self.all_args,
                             self.envs.observation_space,
                             self.envs.action_space,
                             device=self.device)
        self.trainer = Trainer(self.all_args, self.policy, device=self.device)
        
        # buffer
        self.buffer = ReplayBuffer(self.all_args,
                                   self.num_agents,
                                   self.envs.observation_space,
                                   self.envs.action_space)

        if self.model_dir is not None:
            self.restore()

    def run(self):
        raise NotImplementedError

    def warmup(self):
        raise NotImplementedError

    def collect(self, step):
        raise NotImplementedError

    def insert(self, data):
        raise NotImplementedError
    
    @torch.no_grad()
    def compute(self):
        self.trainer.prep_rollout()
        next_values = self.trainer.policy.get_values(np.concatenate(self.buffer.obs[-1]), 
                                                     np.concatenate(self.buffer.rnn_states_critic[-1]))
        next_values = np.array(np.split(_t2n(next_values), self.buffer.n_rollout_threads))
        self.buffer.compute_returns(next_values)

    def train(self):
        self.trainer.prep_training()
        train_infos = self.trainer.train(self.buffer)      
        self.buffer.after_update()
        return train_infos

    def save(self):
        # policy_actor = self.trainer.policy.actor
        # torch.save(policy_actor.state_dict(), str(self.save_dir) + "/actor.pt")
        # policy_critic = self.trainer.policy.critic
        # torch.save(policy_critic.state_dict(), str(self.save_dir) + "/critic.pt")
        policy_actor = self.trainer.policy.actor
        torch.save(policy_actor, str(self.save_dir) + "/actor.pth")
        policy_critic = self.trainer.policy.critic
        torch.save(policy_critic, str(self.save_dir) + "/critic.pth")

    def restore(self):
        # policy_actor_state_dict = torch.load(str(self.model_dir) + '/actor_agent.pt')
        # self.policy.actor.load_state_dict(policy_actor_state_dict)
        # policy_critic_state_dict = torch.load(str(self.model_dir) + '/critic_agent.pt')
        # self.policy.critic.load_state_dict(policy_critic_state_dict)
        self.policy.actor = torch.load(str(self.model_dir) + '/actor.pth')
        self.policy.critic = torch.load(str(self.model_dir) + '/critic.pth')


    def log_info(self, infos, total_num_steps):
        if self.use_wandb:
            for k, v in infos.items():
                wandb.log({k: v}, step=total_num_steps)
        else:
            # ic(total_num_steps, train_infos)
            pass