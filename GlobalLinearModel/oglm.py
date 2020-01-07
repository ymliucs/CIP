# -*- coding: utf-8 -*-

import pickle
import random
from collections import Counter
from datetime import datetime, timedelta

import numpy as np


class GlobalLinearModel(object):

    def __init__(self, nt):
        # 词性数量
        self.nt = nt

    def create_feature_space(self, data):
        # 特征空间
        self.epsilon = list({
            f for wiseq, tiseq in data
            for f in set(self.instantiate(wiseq, 0, -1)).union(
                *[self.instantiate(wiseq, i, tiseq[i - 1])
                  for i, ti in enumerate(tiseq[1:], 1)]
            )
        })
        # 特征对应索引的字典
        self.fdict = {f: i for i, f in enumerate(self.epsilon)}
        # 特征空间维度
        self.d = len(self.epsilon)

        # 特征权重
        self.W = np.zeros((self.d, self.nt))
        # 累加特征权重
        self.V = np.zeros((self.d, self.nt))
        # Bigram特征
        self.BF = [self.bigram(prev_ti) for prev_ti in range(self.nt)]

    def online(self, trainset, devset, file, epochs, interval, average):
        # 记录迭代时间
        total_time = timedelta()
        # 记录最大准确率及对应的迭代次数
        max_e, max_accuracy = 0, 0.0

        # 迭代指定次数训练模型
        for epoch in range(1, epochs + 1):
            start = datetime.now()
            # 随机打乱数据
            random.shuffle(trainset)
            # 保存更新时间戳和每个特征最近更新时间戳的记录
            self.k, self.R = 0, np.zeros((self.d, self.nt), dtype='int')
            for batch in trainset:
                self.update(batch)
            self.V += [(self.k - r) * w for r, w in zip(self.R, self.W)]

            print("Epoch %d / %d: " % (epoch, epochs))
            tp, total, accuracy = self.evaluate(trainset, average=average)
            print("%-6s %d / %d = %4f" % ('train:', tp, total, accuracy))
            tp, total, accuracy = self.evaluate(devset, average=average)
            print("%-6s %d / %d = %4f" % ('dev:', tp, total, accuracy))
            t = datetime.now() - start
            print("%ss elapsed\n" % t)
            total_time += t

            # 保存效果最好的模型
            if accuracy > max_accuracy:
                self.dump(file)
                max_e, max_accuracy = epoch, accuracy
            elif epoch - max_e > interval:
                break
        print("max accuracy of dev is %4f at epoch %d" %
              (max_accuracy, max_e))
        print("mean time of each epoch is %ss\n" % (total_time / epoch))

    def update(self, batch):
        wiseq, tiseq = batch
        # 根据现有权重向量预测词性序列
        piseq = self.predict(wiseq)
        # 如果预测词性序列与正确词性序列不同，则更新权重
        if not np.array_equal(tiseq, piseq):
            prev_ti, prev_pi = -1, -1
            for i, (ti, pi) in enumerate(zip(tiseq, piseq)):
                cfreqs = Counter(self.instantiate(wiseq, i, prev_ti))
                # 统计正确词性不同权重出现的次数
                cfis, cfcounts = map(list, zip(*[
                    (self.fdict[f], cfreqs[f])
                    for f in cfreqs if f in self.fdict
                ]))
                prev_w, prev_r = self.W[cfis, ti], self.R[cfis, ti]
                # 累加权重加上步长乘以权重
                self.V[cfis, ti] += (self.k - prev_r) * prev_w
                # 更新正确词性对应权重
                self.W[cfis, ti] += cfcounts
                # 更新时间戳记录
                self.R[cfis, ti] = self.k

                efreqs = Counter(self.instantiate(wiseq, i, prev_pi))
                # 统计预测词性不同权重出现的次数
                efis, efcounts = map(list, zip(*[
                    (self.fdict[f], efreqs[f])
                    for f in efreqs if f in self.fdict
                ]))
                prev_w, prev_r = self.W[efis, pi], self.R[efis, pi]
                # 累加权重加上步长乘以权重
                self.V[efis, pi] += (self.k - prev_r) * prev_w
                # 更新预测词性对应权重
                self.W[efis, pi] -= efcounts
                # 更新时间戳记录
                self.R[efis, pi] = self.k

                prev_ti, prev_pi = ti, pi
            self.k += 1

    def predict(self, wiseq, average=False):
        T = len(wiseq)
        delta = np.zeros((T, self.nt))
        paths = np.zeros((T, self.nt), dtype='int')
        bscores = np.array([self.score(bfv, average) for bfv in self.BF])

        fv = self.instantiate(wiseq, 0, -1)
        delta[0] = self.score(fv, average)

        for i in range(1, T):
            uscores = self.score(self.unigram(wiseq, i), average)
            scores = np.transpose(bscores + uscores) + delta[i - 1]
            paths[i] = np.argmax(scores, axis=1)
            delta[i] = scores[np.arange(self.nt), paths[i]]
        prev = np.argmax(delta[-1])

        predict = [prev]
        for i in reversed(range(1, T)):
            prev = paths[i, prev]
            predict.append(prev)
        predict.reverse()
        return predict

    def score(self, fvector, average=False):
        # 获取特征索引
        fiseq = [self.fdict[f] for f in fvector if f in self.fdict]
        # 计算特征对应权重得分
        scores = self.V[fiseq] if average else self.W[fiseq]
        return np.sum(scores, axis=0)

    def bigram(self, prev_ti):
        return [('01', prev_ti)]

    def unigram(self, wiseq, index):
        word = wiseq[index]
        prev_word = wiseq[index - 1] if index > 0 else '^^'
        next_word = wiseq[index + 1] if index < len(wiseq) - 1 else '$$'
        prev_char = prev_word[-1]
        next_char = next_word[0]
        first_char = word[0]
        last_char = word[-1]

        fvector = []
        fvector.append(('02', word))
        fvector.append(('03', prev_word))
        fvector.append(('04', next_word))
        fvector.append(('05', word, prev_char))
        fvector.append(('06', word, next_char))
        fvector.append(('07', first_char))
        fvector.append(('08', last_char))

        for char in word[1:-1]:
            fvector.append(('09', char))
            fvector.append(('10', first_char, char))
            fvector.append(('11', last_char, char))
        if len(word) == 1:
            fvector.append(('12', word, prev_char, next_char))
        for i in range(1, len(word)):
            prev_char, char = word[i - 1], word[i]
            if prev_char == char:
                fvector.append(('13', char, 'consecutive'))
            if i <= 4:
                fvector.append(('14', word[:i]))
                fvector.append(('15', word[-i:]))
        if len(word) <= 4:
            fvector.append(('14', word))
            fvector.append(('15', word))
        return fvector

    def instantiate(self, wiseq, index, prev_ti):
        bigram = self.bigram(prev_ti)
        unigram = self.unigram(wiseq, index)
        return bigram + unigram

    def evaluate(self, data, average=False):
        tp, total = 0, 0

        for wiseq, tiseq in data:
            total += len(wiseq)
            piseq = np.array(self.predict(wiseq, average))
            tp += np.sum(tiseq == piseq)
        accuracy = tp / total
        return tp, total, accuracy

    def dump(self, file):
        with open(file, 'wb') as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, file):
        with open(file, 'rb') as f:
            glm = pickle.load(f)
        return glm