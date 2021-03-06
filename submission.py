from netsapi.challenge import *
import pandas as pd
import numpy as np
import itertools
from sklearn.gaussian_process import GaussianProcessRegressor
import xgboost


class RemyGA:
  '''
    Simple Genetic Algorithm. 
    https://github.com/slremy/estool/
  '''
  def __init__(self, num_params,      # number of model parameters
               random_individuals_fcn,
               mutate_fcn,
               immigrant_ratio=.2,     # percentage of new individuals
               sigma_init=0.1,        # initial standard deviation
               sigma_decay=0.999,     # anneal standard deviation
               sigma_limit=0.01,      # stop annealing if less than this
               popsize=256,           # population size
               elite_ratio=0.1,       # percentage of the elites
               forget_best=False,     # forget the historical best elites
               weight_decay=0.01,     # weight decay coefficient
              ):

    self.num_params = num_params
    self.sigma_init = sigma_init
    self.sigma_decay = sigma_decay
    self.sigma_limit = sigma_limit
    self.popsize = popsize
    self.random_individuals_fcn = random_individuals_fcn
    self.mutate_fcn = mutate_fcn
    self.solutions = None

    self.elite_ratio = elite_ratio
    self.elite_popsize = int(self.popsize * self.elite_ratio)
    self.immigrant_ratio = immigrant_ratio
    self.immigrant_popsize = int(self.popsize * self.immigrant_ratio)

    self.sigma = self.sigma_init
    self.elite_params = np.zeros((self.elite_popsize, self.num_params))
    #self.elite_rewards = np.zeros(self.elite_popsize)
    self.best_param = np.zeros(self.num_params)
    self.best_reward = 0
    self.reward_pdf = np.zeros(self.popsize+1)
    self.solutions = np.zeros((self.popsize, self.num_params))
    self.first_iteration = True
    self.forget_best = forget_best
    self.weight_decay = weight_decay

  def rms_stdev(self):
    return self.sigma # same sigma for all parameters.

  def ask(self, process=lambda x:x):
    '''returns a list of parameters'''
    self.epsilon = np.random.randn(self.popsize, self.num_params) * self.sigma
    
    
    def mate(a, b):
      #single point crossover
      c = np.copy(a)
      idx = np.where(np.random.rand((c.size)) > 0.5)
      c[idx] = b[idx]
      return c
    
    def crossover(a,b):
      cross_point = int((self.num_params-1)*np.random.rand(1));
      c = np.append(a[:cross_point], b[cross_point:self.num_params]);
      return c
    
    index_array = np.arange(self.popsize)
    if self.first_iteration:
        self.solutions = process(self.random_individuals_fcn(self.popsize,self.num_params))
    else:
        #intialize the index list for "mating" chromosomes
        childrenIDX = range(self.popsize - self.elite_popsize - self.immigrant_popsize);
        selected = np.arange(2*len(childrenIDX));
        for i in range(len(selected)):
            testNo = 1;
            #Choose a parent
            while self.reward_pdf[testNo] < np.random.rand():
                testNo = testNo + 1;
            selected[i] = index_array[testNo];
        children = []
        for i in range(len(childrenIDX)):
            chromosomeA = self.solutions[selected[i*2+0], :];
            chromosomeB = self.solutions[selected[i*2+1], :];
            child = crossover(chromosomeA,chromosomeB) if 0.5 < np.random.rand() else crossover(chromosomeB,chromosomeA)
            children.append(self.mutate_fcn(child))
        
        self.solutions = process(np.concatenate((self.elite_params, self.random_individuals_fcn(self.immigrant_popsize,self.num_params), np.array(children))))

    return self.solutions

  def tell(self, reward_table_result):
    # input must be a numpy float array
    assert(len(reward_table_result) == self.popsize), "Inconsistent reward_table size reported."

    reward_table = np.array(reward_table_result)
    
    if self.weight_decay > 0:
      l2_decay = compute_weight_decay(self.weight_decay, self.solutions)
      reward_table += l2_decay

    reward = reward_table
    solution = self.solutions

    reward_masked = np.ma.masked_array(reward,mask = (np.isnan(reward) | np.isinf(reward)))
    
    self.reward_pdf = (np.cumsum(reward_masked)/np.sum(reward_masked)).compressed()
    sorted_idx = np.argsort(reward_masked)[::-1]
    idx = sorted_idx[~reward_masked.mask][0:self.elite_popsize]
    
    assert(len(idx) == self.elite_popsize), "Inconsistent elite size reported."
    
    self.elite_rewards = reward[idx]
    self.elite_params = solution[idx]

    self.curr_best_reward = self.elite_rewards[0]
    
    if self.first_iteration or (self.curr_best_reward > self.best_reward):
      self.first_iteration = False
      self.best_reward = self.elite_rewards[0]
      self.best_param = np.copy(self.elite_params[0])

    if (self.sigma > self.sigma_limit):
      self.sigma *= self.sigma_decay

    self.first_iteration = False

  def current_param(self):
    return self.elite_params[0]

  def set_mu(self, mu):
    pass

  def best_param(self):
    return self.best_param

  def result(self): # return best params so far, along with historically best reward, curr reward, sigma
    return (self.best_param, self.best_reward, self.curr_best_reward, self.sigma)


def mutate(chromosome):
    mutation_rate = .5
    for j in range(chromosome.shape[0]):
        r = np.random.rand(1);
        if(r > mutation_rate):
            chromosome[j] = np.remainder(chromosome[j]+np.random.randn(1),0.99);
    return chromosome

def make_random_individuals(x,y):
    value=np.random.rand(x,y);
    return value

def boundary(individual):
    processed = individual%(1+np.finfo(float).eps)
    return processed


class SRGAAgent():
    def __init__(self, environment):
        self._epsilon = 0.2  # 20% chances to apply a random action
        self._gamma = 0.99  # Discounting factor
        self._alpha = 0.5  # soft update param
        self.environment = environment #self._env = env
        self._resolution = .1#self.environment.resolution
        
        self.popsize=10
        self.num_paramters = 30
        self.solver = RemyGA(self.num_paramters,         # number of model parameters
                random_individuals_fcn=make_random_individuals,
                mutate_fcn = mutate,
                sigma_init=1,          # initial standard deviation
                popsize=self.popsize,       # population size
                elite_ratio=0.2,       # percentage of the elites
                forget_best=False,     # forget the historical best elites
                weight_decay=0.00,     # weight decay coefficient
                )
    def stateSpace(self):
        return range(1,self.environment.policyDimension+1)

    def train(self):
        allrewards = []
        allpolicies = []
        for episode in range(20):
            rewards = []
            
            if episode % self.popsize == 0:
                # ask for a set of random candidate solutions to be evaluated
                solutions = self.solver.ask(boundary)
            
                #convert an array of 10 floats into a policy of itn, irs per year for 5 years
                policies = []
                for v in solutions:
                    actions = [i for i in itertools.zip_longest(*[iter(v)] * 2, fillvalue="")]
                    policy = {i+1: list(actions[i]) for i in range(5)}
                    policies.append(policy)

                # calculate the reward for each given solution using the environment's method
                batchRewards = self.environment.evaluatePolicy(policies)
                # raise Exception(batchRewards)
                rewards.append(batchRewards)

                self.solver.tell(batchRewards)

                allrewards.extend(batchRewards)
                allpolicies.extend(policies)
        # gp = GaussianProcessRegressor()
        X = []
        for p in allpolicies:
            tmp_X = []
            for k, v in p.items():
                tmp_X.extend(v)
            X.append(tmp_X)
        allrewards = [r / 100.0 for r in allrewards]
        # gp.fit(X, allrewards)
        best_xgb_model = xgboost.XGBRegressor(colsample_bytree=0.4,
                 gamma=0,                 
                 learning_rate=0.07,
                 max_depth=3,
                 min_child_weight=1.5,
                 n_estimators=10000,                                                                    
                 reg_alpha=0.75,
                 reg_lambda=0.45,
                 subsample=0.6,
                 seed=42)
        best_xgb_model.fit(X,allrewards)
        allrewards = []
        allpolicies = []
        for episode in range(100):
            rewards = []
            
            if episode % self.popsize == 0:
                # ask for a set of random candidate solutions to be evaluated
                solutions = self.solver.ask(boundary)
            
                #convert an array of 10 floats into a policy of itn, irs per year for 5 years
                policies = []
                for v in solutions:
                    actions = [i for i in itertools.zip_longest(*[iter(v)] * 2, fillvalue="")]
                    policy = {i+1: list(actions[i]) for i in range(5)}
                    policies.append(policy)

                # calculate the reward for each given solution using the environment's method
                batchRewards = []
                for p in policies:
                    tmp_p = []
                    for k, v in p.items():
                        tmp_p.extend(v)
                    # batchRewards.append(gp.sample_y(np.array(tmp_p).reshape(1, -1))[0][0] * 100)
                    batchRewards.append(best_xgb_model.predict(tmp_p) * 100)
                print(batchRewards)
                rewards.append(batchRewards)

                self.solver.tell(batchRewards)

                allrewards.extend(batchRewards)
                allpolicies.extend(policies)

        return np.array(allrewards)

    def generate(self):
        self.train()
        #generate a policy from the array used to represent the candidate solution
        actions = [i for i in itertools.zip_longest(*[iter(self.solver.best_param)] * 2, fillvalue="")]
        best_policy = {state: list(actions[state-1]) for state in self.stateSpace()}
        best_reward = self.environment.evaluatePolicy(best_policy)
        print(best_policy, best_reward)
        return best_policy, best_reward


"""
env = ChallengeProveEnvironment(experimentCount=105)
a = SRGAAgent(env)
finalpolicy, episodicreward = a.generate()
"""
EvaluateChallengeSubmission(ChallengeProveEnvironment, SRGAAgent, "SRGAAgent_20.csv")
