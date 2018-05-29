#!/usr/bin/env python3
import numpy as np
import tensorflow as tf
import morpho_dataset


class Network:
    def __init__(self, threads, seed=42):
        # Create an empty graph and a session
        graph = tf.Graph()
        graph.seed = seed
        self.session = tf.Session(graph = graph, config=tf.ConfigProto(inter_op_parallelism_threads=threads,
                                                                       intra_op_parallelism_threads=threads))

    def construct(self, args, num_words, num_chars, num_ne):
        with self.session.graph.as_default():
            
            
            # Inputs
            self.sentence_lens = tf.placeholder(tf.int32, [None], name="sentence_lens")
            self.word_ids = tf.placeholder(tf.int32, [None, None], name="word_ids")
            self.charseqs = tf.placeholder(tf.int32, [None, None], name="charseqs")
            self.charseq_lens = tf.placeholder(tf.int32, [None], name="charseq_lens")
            self.charseq_ids = tf.placeholder(tf.int32, [None, None], name="charseq_ids")
            self.ne = tf.placeholder(tf.int32, [None, None], name="ne")
            self.is_training = tf.placeholder(tf.bool, [], name="is_training")

            # TODO(we): Choose RNN cell class according to args.rnn_cell (LSTM and GRU
            # should be supported, using tf.nn.rnn_cell.{BasicLSTM,GRU}Cell).
            num_units = args.rnn_cell_dim
            if args.rnn_cell == 'RNN':
                cell_fw = tf.nn.rnn_cell.BasicRNNCell(num_units)
                cell_bw = tf.nn.rnn_cell.BasicRNNCell(num_units)
                
            elif args.rnn_cell == 'LSTM':
                cell_fw = tf.nn.rnn_cell.BasicLSTMCell(num_units)
                cell_bw = tf.nn.rnn_cell.BasicLSTMCell(num_units)
                
            else: # Problem when gru selected again. why only 40% acc
                # ?????????
                cell_fw = tf.nn.rnn_cell.GRUCell(num_units)
                cell_bw = tf.nn.rnn_cell.GRUCell(num_units)            
            
            # Add dropout
            cell_fw = tf.nn.rnn_cell.DropoutWrapper(cell_fw, input_keep_prob=1-args.dropout, output_keep_prob=1-args.dropout)
            cell_bw = tf.nn.rnn_cell.DropoutWrapper(cell_bw, input_keep_prob=1-args.dropout, output_keep_prob=1-args.dropout)
            # Create word embeddings for num_words of dimensionality args.we_dim
            # using `tf.get_variable`.
            word_embeddings = tf.get_variable('word_embeddings', [num_words, args.we_dim])
            
            # Embed self.word_ids according to the word embeddings, by utilizing
            # `tf.nn.embedding_lookup`.
            embedded_words = tf.nn.embedding_lookup(word_embeddings, self.word_ids) # which word ids?

            # Convolutional word embeddings (CNNE)

            # Generate character embeddings for num_chars of dimensionality args.cle_dim.
            char_embeddings = tf.get_variable('char_embeddings', [num_chars, args.cle_dim])
            
            # Embed self.charseqs (list of unique words in the batch) using the character embeddings.
            embedded_chars = tf.nn.embedding_lookup(char_embeddings, self.charseqs)
            #print(embedded_chars)
            # TODO: For kernel sizes of {2..args.cnne_max}, do the following:
            # - use `tf.layers.conv1d` on input embedded characters, with given kernel size
            #   and `args.cnne_filters`; use `VALID` padding, stride 1 and no activation.
            # - perform channel-wise max-pooling over the whole word, generating output
            #   of size `args.cnne_filters` for every word.
            #cnn_filter_no = 0
            outputs = []
            
            # uncomment to manually to 1d conv
            #embedded_chars_ = tf.expand_dims(embedded_chars, axis=1) # change to shape [n, 1, max_len, dim], so its like an image of height one
            #print('expanded in', embedded_chars_)
            for kernel_size in range(2, args.cnne_max + 1):
                # Manual 1d conv
                #filter_ = tf.get_variable('conv_filter'+str(kernel_size), shape=[1, kernel_size, args.cle_dim, args.cnne_filters])
                #output = tf.nn.conv2d(embedded_chars_, filter_, strides=[1,1,1,1], padding='VALID', name='cnne_layer_'+str(kernel_size))
                #output = tf.squeeze(output, axis=1) # remove extra dim
                #print(output)
                 
                #output = tf.layers.conv1d(embedded_chars, args.cnne_filters, kernel_size, strides=1, padding='VALID', name='cnne_layer_'+str(kernel_size))
                output = tf.layers.conv1d(embedded_chars, args.cnne_filters, kernel_size, strides=1, padding='VALID', activation=None, use_bias=False, name='cnne_layer_'+str(kernel_size))
                
                # Apply batch norm
                if args.bn:
                    output = tf.layers.batch_normalization(output, training=self.is_training, name='cnn_layer_BN_'+str(kernel_size))
                output = tf.nn.relu(output, name='cnn_layer_relu_'+str(kernel_size))
                pooling = tf.reduce_max(output, axis=1)
                
                #print(pooling)
                #cnn_layer_no += 1
                outputs.append(pooling)
                
                
            # TODO: Concatenate the computed features (in the order of kernel sizes 2..args.cnne_max).
            # Consequently, each word from `self.charseqs` is represented using convolutional embedding
            # (CNNE) of size `(args.cnne_max-1)*args.cnne_filters`.
            concat_output = tf.concat(outputs, axis=-1)
            #print(concat_output)
            # TODO: Generate CNNEs of all words in the batch by indexing the just computed embeddings
            # by self.charseq_ids (using tf.nn.embedding_lookup).
            cnne = tf.nn.embedding_lookup(concat_output, self.charseq_ids)
            #print('cnne', cnne)
            # TODO: Concatenate the word embeddings (computed above) and the CNNE (in this order).
            embedded_inputs = tf.concat([embedded_words, cnne], axis=-1)
            #print('emb in', embedded_inputs)
            # TODO(we): Using tf.nn.bidirectional_dynamic_rnn, process the embedded inputs.
            # Use given rnn_cell (different for fwd and bwd direction) and self.sentence_lens.
            outputs, _ = tf.nn.bidirectional_dynamic_rnn(cell_fw=cell_fw, cell_bw=cell_bw, inputs=embedded_inputs, sequence_length=self.sentence_lens, dtype=tf.float32)
            #output1 = tf.nn.batch_normalization(outputs[0], training=self.is_training, name='birnn_bn1'+str(kernel_size))
            #output1 = tf.nn.relu(output1, name='birnn_relu1'+str(kernel_size))
            #output2 = tf.nn.batch_normalization(outputs[0], training=self.is_training, name='birnn_bn2'+str(kernel_size))
            #output2 = tf.nn.relu(output2, name='birnn_relu2'+str(kernel_size))
            # TODO(we): Concatenate the outputs for fwd and bwd directions (in the third dimension).
            #output = tf.concat([output1, output2], axis=-1)
            
            output = tf.concat(outputs, axis=-1)
            
            # TODO(we): Add a dense layer (without activation) into num_ne classes and
            # store result in `output_layer`.
            output_layer = tf.layers.dense(output, num_ne) 

            # TODO(we): Generate `self.predictions`.
            self.predictions = tf.argmax(output_layer, axis=-1) # 3rd dim!

            # TODO(we): Generate `weights` as a 1./0. mask of valid/invalid words (using `tf.sequence_mask`).
            weights = tf.sequence_mask(self.sentence_lens, dtype=tf.float32)

            # Training
 
            # TODO(we): Define `loss` using `tf.losses.sparse_softmax_cross_entropy`, but additionally
            # use `weights` parameter to mask-out invalid words.
            loss = tf.losses.sparse_softmax_cross_entropy(labels=self.ne, logits=output_layer, weights=weights)
            global_step = tf.train.create_global_step()
             
            # Choose optimizer
            #if args.optimizer == "SGD" and args.momentum:
                #self.training = tf.train.MomentumOptimizer(learning_rate, momentum=args.momentum).minimize(loss, global_step=global_step, name="momentum")                
            #elif args.optimizer == "SGD":
                #self.training = tf.train.GradientDescentOptimizer(args.learning_rate).minimize(loss, global_step=global_step, name="sgd")
            #else:                
                #self.training = tf.train.AdamOptimizer(args.learning_rate).minimize(loss, global_step=global_step, name="adam")
                
            optimizer = tf.train.AdamOptimizer()
            # Note how instead of `optimizer.minimize` we first get the # gradients using
            # `optimizer.compute_gradients`, then optionally clip them and
            # finally apply then using `optimizer.apply_gradients`.
            gradients, variables = zip(*optimizer.compute_gradients(loss))
            # TODO: Compute norm of gradients using `tf.global_norm` into `gradient_norm`.
            gradient_norm = tf.global_norm(gradients) 
            # TODO: If args.clip_gradient, clip gradients (back into `gradients`) using `tf.clip_by_global_norm`.            
            if args.clip_gradient is not None:
                gradients, _ = tf.clip_by_global_norm(gradients, clip_norm=args.clip_gradient, use_norm=gradient_norm)
            self.training = optimizer.apply_gradients(zip(gradients, variables), global_step=global_step)
           
             
            # Summaries
            self.current_accuracy, self.update_accuracy = tf.metrics.accuracy(self.ne, self.predictions, weights=weights)
            self.current_precision, self.update_precision = tf.metrics.precision(self.ne, self.predictions, weights=weights)
            self.current_recall, self.update_recall = tf.metrics.recall(self.ne, self.predictions, weights=weights)
            self.current_loss, self.update_loss = tf.metrics.mean(loss, weights=tf.reduce_sum(weights))
            self.reset_metrics = tf.variables_initializer(tf.get_collection(tf.GraphKeys.METRIC_VARIABLES))

            summary_writer = tf.contrib.summary.create_file_writer(args.logdir, flush_millis=10 * 1000)
            self.summaries = {}
            with summary_writer.as_default(), tf.contrib.summary.record_summaries_every_n_global_steps(10):
                self.summaries["train"] = [tf.contrib.summary.scalar("train/loss", self.update_loss),
                                           tf.contrib.summary.scalar("train/gradient_norm", gradient_norm),
                                           tf.contrib.summary.scalar("train/accuracy", self.update_accuracy),
                                           tf.contrib.summary.scalar("train/precision", self.update_precision),
                                           tf.contrib.summary.scalar("train/recall", self.update_recall)]
            with summary_writer.as_default(), tf.contrib.summary.always_record_summaries():
                for dataset in ["dev", "test"]:
                    self.summaries[dataset] = [tf.contrib.summary.scalar(dataset + "/loss", self.current_loss),
                                               tf.contrib.summary.scalar(dataset + "/accuracy", self.current_accuracy),
                                               tf.contrib.summary.scalar(dataset + "/precision", self.current_precision),
                                               tf.contrib.summary.scalar(dataset + "/recall", self.current_recall)
                                               ]

            # Initialize variables
            self.session.run(tf.global_variables_initializer())
            with summary_writer.as_default():
                tf.contrib.summary.initialize(session=self.session, graph=self.session.graph)

    def train_epoch(self, train, batch_size):
        while not train.epoch_finished():
            sentence_lens, word_ids, charseq_ids, charseqs, charseq_lens = train.next_batch(batch_size, including_charseqs=True)
            self.session.run(self.reset_metrics)
            self.session.run([self.training, self.summaries["train"]],
                             {self.sentence_lens: sentence_lens,
                              self.charseqs: charseqs[train.FORMS], self.charseq_lens: charseq_lens[train.FORMS],
                              self.word_ids: word_ids[train.FORMS], self.charseq_ids: charseq_ids[train.FORMS],
                              self.ne: word_ids[train.NE], self.is_training: True})

    def evaluate(self, dataset_name, dataset, batch_size):
        self.session.run(self.reset_metrics)
        while not dataset.epoch_finished():
            sentence_lens, word_ids, charseq_ids, charseqs, charseq_lens = dataset.next_batch(batch_size, including_charseqs=True)
            self.session.run([self.update_accuracy, self.update_precision, self.update_recall, self.update_loss],
                             {self.sentence_lens: sentence_lens,
                              self.charseqs: charseqs[train.FORMS], self.charseq_lens: charseq_lens[train.FORMS],
                              self.word_ids: word_ids[train.FORMS], self.charseq_ids: charseq_ids[train.FORMS],
                              self.ne: word_ids[train.NE], self.is_training: False})
        return self.session.run([self.current_accuracy, self.current_precision, self.current_recall, self.summaries[dataset_name]]) 

    def predict(self, dataset, batch_size):
        tags = []
        while not dataset.epoch_finished():
            sentence_lens, word_ids, charseq_ids, charseqs, charseq_lens = dataset.next_batch(batch_size, including_charseqs=True)
            tags.extend(self.session.run(self.predictions,
                                         {self.sentence_lens: sentence_lens,
                                          self.charseqs: charseqs[train.FORMS], self.charseq_lens: charseq_lens[train.FORMS],
                                          self.word_ids: word_ids[train.FORMS], self.charseq_ids: charseq_ids[train.FORMS], 
                                          self.is_training: False}))
        return tags


if __name__ == "__main__":
    import argparse
    import datetime
    import os
    import re

    # Fix random seed
    np.random.seed(42)

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch_size", default=10, type=int, help="Batch size.")
    parser.add_argument("--cle_dim", default=32, type=int, help="Character-level embedding dimension.")
    parser.add_argument("--cnne_filters", default=16, type=int, help="CNN embedding filters per length.")
    parser.add_argument("--optimizer", default="Adam", type=str, help="Optimizer.")    
    parser.add_argument("--cnne_max", default=4, type=int, help="Maximum CNN filter length.")
    parser.add_argument("--epochs", default=10, type=int, help="Number of epochs.")
    parser.add_argument("--recodex", default=False, action="store_true", help="ReCodEx mode.")
    parser.add_argument("--rnn_cell", default="LSTM", type=str, help="RNN cell type.")
    parser.add_argument("--rnn_cell_dim", default=64, type=int, help="RNN cell dimension.")
    parser.add_argument("--threads", default=1, type=int, help="Maximum number of threads to use.")
    parser.add_argument("--we_dim", default=64, type=int, help="Word embedding dimension.")
    parser.add_argument("--learning_rate", default=0.01, type=float, help="Initial learning rate.")
    parser.add_argument("--learning_rate_final", default=None, type=float, help="Final learning rate.")
    parser.add_argument("--momentum", default=None, type=float, help="Momentum.")
    parser.add_argument("--dropout", default=0, type=float, help="Dropout rate.")
    parser.add_argument("--bn", default=False, type=bool, help="Batch normalization.")
    parser.add_argument("--clip_gradient", default=None, type=float, help="Norm for gradient clipping.")
    
    args = parser.parse_args()

    # Create logdir name
    args.logdir = "logs/{}-{}-{}".format(
        os.path.basename(__file__),
        datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S"),
        ",".join(("{}={}".format(re.sub("(.)[^_]*_?", r"\1", key), value) for key, value in sorted(vars(args).items())))
    )
    if not os.path.exists("logs"): os.mkdir("logs") # TF 1.6 will do this by itself

    # Load the data
    train = morpho_dataset.MorphoDataset("esp.train")
    dev = morpho_dataset.MorphoDataset("esp.testa", train=train, shuffle_batches=False)
    test = morpho_dataset.MorphoDataset("esp.testb", train=train, shuffle_batches=False)

    print(len(train.factors[train.FORMS].words), len(train.factors[train.FORMS].alphabet),
                      len(train.factors[train.NE].words))
    
    print(train.factors[train.NE].words)
    
    # Construct the network
    network = Network(threads=args.threads)
    network.construct(args, len(train.factors[train.FORMS].words), len(train.factors[train.FORMS].alphabet),
                      len(train.factors[train.NE].words))

    # Train
    for i in range(args.epochs):
        print("epoch ", i)
        network.train_epoch(train, args.batch_size)
        accuracy, precision, recall, _ = network.evaluate("dev", dev, args.batch_size)
        print("accuracy = {:.2f}".format(100 * accuracy))
        print("precision = {:.2f}".format(100 * precision))
        print("recall = {:.2f}".format(100 * recall))
    
    
    ## Predict test data
    #with open("{}/tagger_sota_test.txt".format(args.logdir), "w") as test_file:
        #forms = test.factors[test.FORMS].strings
        #tags = network.predict(test, args.batch_size)
        #for s in range(len(forms)):
            #for i in range(len(forms[s])):
                #print("{}\t_\t{}".format(forms[s][i], test.factors[test.TAGS].words[tags[s][i]]), file=test_file)
            #print("", file=test_file)
