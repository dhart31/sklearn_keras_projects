#!/usr/bin/env python
# coding: utf-8

# # Predicting diabetes risk
# 
# Diabetes is an extremely common chronic disease in the United States. It's also extremely taxing on the people who have it, both physically as well as economically. Given this, it might be worth exploring whether the risk of diabetes can be predicted with data. To explore the risk factors for diabetes, I will use the Behavioral Risk Factor Surveillance System (BRFSS) from 2015.
# 
# In this notebook, I will try to accomplish the suggested research questions provided on [Kaggle](https://www.kaggle.com/datasets/alexteboul/diabetes-health-indicators-dataset?select=diabetes_012_health_indicators_BRFSS2015.csv): 
# 
# 
# 1. Can survey questions from the BRFSS provide accurate predictions of whether an individual has diabetes?
# 2. What risk factors are most predictive of diabetes risk?
# 3. Can we use a subset of the risk factors to accurately predict whether an individual has diabetes?
# 
# 

# In[75]:


import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import tensorflow as tf
import keras_tuner as kt
from keras_tuner.tuners import BayesianOptimization
from tensorflow import keras
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import *
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn import metrics

from keras.wrappers.scikit_learn import KerasClassifier, KerasRegressor
import eli5
from eli5.sklearn import PermutationImportance


# In[2]:


data = pd.read_csv("diabetes_binary_health_indicators_BRFSS2015.csv")


# As a crude first pass, since I am dealing with ordinal and binary data, I can look at how they are related using a Spearman correlation.

# In[5]:


plt.figure(figsize=(10,10))
sns.heatmap(data=data.corr(method='spearman'),vmin = -0.2, vmax = 0.4, square=True)


# Not surprisingly, diabetes is correlated with poor health markers such as high blood pressure, BMI and cholesterol, and with poor health behaviors such as smoking and lack of exercise. However there are no variables with clear outsized importance, suggesting that the causation of diabetes is complex and multifaceted.

# ## 1. Can survey questions accurately predict diabetes?
# 
# Since I am predicting a category for labeled data with a relatively large number of samples, I'll try using a simple neural network

# In[6]:


X = data.drop(['Diabetes_binary'],axis=1)
X_sc = MinMaxScaler().fit_transform(X)
y = data['Diabetes_binary']

X_train, X_test, y_train, y_test = train_test_split(X_sc, y, test_size=0.20, random_state=123)


# In[51]:


def build_model(hp):
    model = tf.keras.Sequential()
    model.add(tf.keras.layers.Dense(hp.Int("input_units",32,512,32),activation='relu'))
    for i in range(hp.Int("n_layers",1,2)):
        model.add(tf.keras.layers.Dense(hp.Int(f"layer_{i}",32,512,32),activation='relu'))
    model.add(tf.keras.layers.Dense(1,activation='sigmoid'))
    model.compile(loss='mse',optimizer='adam',metrics=['accuracy'])
    return model

tuner = BayesianOptimization(
    build_model,
    objective = "val_accuracy",
    max_trials = 10,
    executions_per_trial = 1,
    directory = "diabetes_risk",
    overwrite=True)

tuner.search(x=X_train,y=y_train,epochs=1,batch_size=256,verbose=1,validation_split=0.33)


# In[56]:


print(tuner.get_best_hyperparameters()[0].values)
best_model = tuner.get_best_models()[0]
history = best_model.fit(X_train, y_train, validation_split = 0.33,epochs=6, batch_size = 256)


# In[57]:


fig = plt.figure(figsize=(12,5))
plt.subplot(221)
plt.plot(history.history['val_loss'])
plt.ylabel('Validation loss')
plt.xlabel('Epochs')

plt.subplot(222)
plt.plot(history.history['val_accuracy'])
plt.ylabel('Validation accuracy')
plt.xlabel('Epochs')


# The accuracy determined with the validation set sits at about 0.86 for all of the epochs, which appears OK. But let's look at the confusion matrix.

# In[58]:


y_pred = best_model.predict(X_test)
conf_mat = metrics.confusion_matrix(y_test,np.round(y_pred))
sns.heatmap(conf_mat,annot=True,cmap='magma')
plt.title('Confusion Matrix')
plt.xlabel("Prediction")
plt.ylabel("Actual")


# Even though the accuracy at first seems "decent", the confusion matrix is bad. There are just as many false positives as there are true positives. The chance of telling somebody that they have diabetes when they actually don't is equally likely. If we just created a model predicting that all the results were negative, what would we get?

# In[36]:


np.sum(y==0)/np.size(y)


# This suggests that our fancy neural network model is not great at all, doing only 0.5% better than the most naive model imaginable. Perhaps the issue is that the model is only good at predicting true negatives, because that is usually what it sees. This is an intrinsic flaw in the input dataset, because it contains mostly negatives. To fix this, I need to rebalance it. The Kaggle page already provides this dataset, but I want to try doing it myself.

# In[37]:


diabetes_group = data[data['Diabetes_binary']==1]
nodiabetes_group = data[data['Diabetes_binary']==0]
diabetes_group_oversampled = diabetes_group.sample(len(nodiabetes_group),replace=True) 

data_oversampled = pd.concat([diabetes_group_oversampled,nodiabetes_group],axis=0)


# In[38]:


fig = plt.figure(figsize=(12,5))
plt.subplot(121)
data['Diabetes_binary'].value_counts().plot(kind='bar',title='Before')
plt.subplot(122)
data_oversampled['Diabetes_binary'].value_counts().plot(kind='bar', title='After')


# This is much better. Let's see if a neural network works better now....

# In[59]:


X_os = data_oversampled.drop(['Diabetes_binary'],axis=1)
X_os_sc = MinMaxScaler().fit_transform(X_os)
y_os = data_oversampled['Diabetes_binary']
X_os_train, X_os_test, y_os_train, y_os_test =train_test_split(X_os_sc, y_os, test_size=0.20, random_state=123)

tuner_os = BayesianOptimization(
    build_model,
    objective = "val_accuracy",
    max_trials = 10,
    executions_per_trial = 1,
    directory = "diabetes_risk",
    overwrite=True)


# In[61]:


tuner_os.search(x=X_os_train,y=y_os_train,epochs=50,batch_size=1024,validation_split=0.33)


# In[64]:


print(tuner_os.get_best_hyperparameters()[0].values)
best_model_os = tuner_os.get_best_models()[0]
history = best_model_os.fit(X_os_train, y_os_train, validation_split = 0.33,epochs=200, batch_size = 2048)


# In[65]:


fig = plt.figure(figsize=(12,5))
plt.subplot(221)
plt.plot(history.history['val_loss'])
plt.ylabel('Validation loss')
plt.xlabel('Epochs')

plt.subplot(222)
plt.plot(history.history['val_accuracy'])
plt.ylabel('Validation accuracy')
plt.xlabel('Epochs')


# In[68]:


y_os_pred = best_model_os.predict(X_os_test)
conf_mat = metrics.confusion_matrix(y_os_test,np.round(y_os_pred))
sns.heatmap(conf_mat,annot=True,cmap='magma')
plt.title('Confusion Matrix')
plt.xlabel("Prediction")
plt.ylabel("Actual")


# In[73]:


test_loss, test_acc = best_model_os.evaluate(X_os_test, y_os_test)
print("Loss: %s" % test_loss)
print("Accuracy: %s" % test_acc)


# This is a much better set of results. True positives and negatives are much more common than false positives and negatives. This is a much better score than the naive method used before would predict: 0.5 (since I artificially oversampled). From this, we can conclude that it is possible to predict diabetes relatively well with survey questions, provided that the dataset is over or undersampled such that the two outcomes are equally probable.

# ## 2. What risk factors are most predictive of diabetes risk?
# 
# There are a lot of ways I could do this. But since I am learning neural networks, let's try using a method that works with them called "permutation importance". This method tests a trained model on datasets where each feature's values are  shuffled to see how it affects the performance. By design, the method is biased toward features that are correlated, but all of the survey questions seem to imply a hypothesized correlation, so this shouldn't be a design flaw here.
# 
# I use the eli5 package to accomplish this, which is supposed to work better with sklearn models. I created a simple wrapper to get it to cooperate quickly.

# In[80]:


my_model = KerasRegressor(build_fn= lambda: best_model_os)
history = my_model.fit(X_os_train, y_os_train, validation_split = 0.33,epochs=200, batch_size = 2048)


# In[81]:


perm = PermutationImportance(my_model, random_state=1).fit(X_os_test,y_os_test)
eli5.show_weights(perm, feature_names = X_os_test.columns.tolist())


# In[82]:


eli5.show_weights(perm, feature_names = X.columns.tolist())


# The importance of each feature seems to gradually decrease; there is no obvious cutoff. This result agrees with the correlation matrix we calculated above: there were no obvious features that stood above the rest. Let's try arbitrarily cutting off the data at the point where the relatively weight is about half of the top value. We can visualize these features easily with seaborn.

# In[83]:


fig = plt.figure(figsize=(12,6))




for i,name in enumerate(['GenHlth','Age','Income']):
    plt.subplot(3,4,i+1)
    sns.boxplot(data=data,x='Diabetes_binary',y=name)

for i,name in enumerate(['HighBP','HighChol','Sex','Smoker','Fruits','DiffWalk','PhysActivity']):
    plt.subplot(3,4,i+4)
    sns.countplot(data=data,x='Diabetes_binary',hue=name)

plt.subplot(3,4,11)
sns.violinplot(data=data,x='Diabetes_binary',y='BMI')
plt.ylim(10,50)
plt.subplot(3,4,12)
sns.violinplot(data=data,x='Diabetes_binary',y='PhysHlth')
    
plt.tight_layout()


# ## 3. Can we use a subset of the risk factors to accurately predict whether an individual has diabetes?
# 
# Let's see if I can get a decent model working with only the top 12 risk factors.

# In[88]:


X_sub = X_os[['HighBP','BMI','GenHlth','Age','Income','HighChol','Sex','PhysHlth','Smoker','Fruits','DiffWalk','PhysActivity']]
X_sub_sc = MinMaxScaler().fit_transform(X_sub)
X_sub_train, X_sub_test, y_sub_train, y_sub_test = train_test_split(X_sub_sc, y_os, test_size=0.20, random_state=123)


# In[89]:


tuner_sub = BayesianOptimization(
    build_model,
    objective = "val_accuracy",
    max_trials = 10,
    executions_per_trial = 1,
    directory = "diabetes_risk",
    overwrite=True)
tuner_sub.search(x=X_sub_train,y=y_sub_train,epochs=150,batch_size=2048,verbose=1,validation_split=0.33)


# In[90]:


print(tuner_sub.get_best_hyperparameters()[0].values)
best_model_sub = tuner_sub.get_best_models()[0]
history = best_model_sub.fit(X_sub_train, y_sub_train, validation_split = 0.33,epochs=200, batch_size = 2048)


# In[91]:


fig = plt.figure(figsize=(12,5))
plt.subplot(221)
plt.plot(history.history['val_loss'])
plt.ylabel('Validation loss')
plt.xlabel('Epochs')

plt.subplot(222)
plt.plot(history.history['val_accuracy'])
plt.ylabel('Validation accuracy')
plt.xlabel('Epochs')


# In[94]:


y_sub_pred = best_model_sub.predict(X_sub_test)
conf_mat = metrics.confusion_matrix(y_sub_test,np.round(y_sub_pred))
sns.heatmap(conf_mat,annot=True,cmap='magma')
plt.title('Confusion Matrix')
plt.xlabel("Prediction")
plt.ylabel("Actual")


# In[96]:


test_loss, test_acc = best_model_sub.evaluate(X_sub_test, y_sub_test)
print("Loss: %s" % test_loss)
print("Accuracy: %s" % test_acc)


# Using half the features, we can get a model with about 86% accuracy. The accuracy decreased by about 3%, which is not bad, considering that the features we removed had significant weight values. 

# In[ ]:




