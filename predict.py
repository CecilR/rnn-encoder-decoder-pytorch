import sys
from utils import *

def load_model():
    src_vocab = load_vocab(sys.argv[2], "src")
    tgt_vocab = load_vocab(sys.argv[3], "tgt")
    tgt_vocab = [x for x, _ in sorted(tgt_vocab.items(), key = lambda x: x[1])]
    enc = encoder(len(src_vocab))
    dec = decoder(len(tgt_vocab))
    enc.eval()
    dec.eval()
    print(enc)
    print(dec)
    load_checkpoint(sys.argv[1], enc, dec)
    return enc, dec, src_vocab, tgt_vocab

def greedy_search(dec, tgt_vocab, data, eos, dec_out, heatmap):
    dec_in = dec_out.topk(1)[1]
    y = dec_in.view(-1).tolist()
    for i in range(len(eos)):
        if eos[i]:
            continue
        if y[i] == EOS_IDX:
            eos[i] = True
            continue
        data[i][3].append(y[i])
        if VERBOSE:
            heatmap[i].append([tgt_vocab[y[i]]] + dec.attn.Va[i][0].tolist())
    return dec_in

def beam_search(dec, tgt_vocab, data, t, eos, dec_out, heatmap):
    p, y = dec_out[:len(eos)].topk(BEAM_SIZE)
    p += Tensor([-10000 if b else a[4] for a, b in zip(data, eos)]).unsqueeze(1)
    if VERBOSE:
        print("\nt = %d\nb =" % t)
        for p0, y0 in zip(p, y):
            print([(round(p1.item(), 4), tgt_vocab[y1]) for p1, y1 in zip(p0, y0)])
    p = p.view(len(eos) // BEAM_SIZE, -1)
    y = y.view(len(eos) // BEAM_SIZE, -1)
    if t == 0:
        p = p[:, :BEAM_SIZE]
        y = y[:, :BEAM_SIZE]
    for i, (p, y) in enumerate(zip(p, y)):
        j = i * BEAM_SIZE
        d0 = data[j:j + BEAM_SIZE]
        d1 = []
        if VERBOSE:
            m0 = heatmap[j:j + BEAM_SIZE]
            m1 = []
        for p, k in zip(*p.topk(BEAM_SIZE)):
            d1.append(d0[k // BEAM_SIZE].copy())
            d1[-1][3] = d1[-1][3] + [y[k]]
            d1[-1][4] = p
            # TODO
            '''
            if VERBOSE:
                m1.append(m0[k // BEAM_SIZE].copy())
                m1[-1].append([tgt_vocab[x[3][-1]]] + dec.attn.Va[i][0].tolist())
            '''
        for _, x in filter(lambda x: eos[j + x[0]], enumerate(d0)):
            d1.append(x)
            if VERBOSE:
                m1.append(m0[k // BEAM_SIZE].copy())
        d1 = sorted(d1, key = lambda x: x[4], reverse = True)[:BEAM_SIZE]
        for k, x in enumerate(d1):
            k += j
            data[k] = x
            eos[k] = x[3][-1] == EOS_IDX
            if VERBOSE:
                heatmap[k].append([tgt_vocab[x[3][-1]]] + dec.attn.Va[i][0].tolist())
        if VERBOSE:
            print("y[%d] =" % i)
            for x in d1:
                print([tgt_vocab[x] for x in x[3]] + [round(x[4].item(), 4)])
    dec_in = [x[3][-1] if len(x[3]) else SOS_IDX for x in data]
    dec_in = LongTensor(dec_in).unsqueeze(1)
    return dec_in

def run_model(enc, dec, tgt_vocab, data):
    t = 0
    eos = [False for _ in data] # number of completed sequences in the batch
    while len(data) < BATCH_SIZE:
        data.append([-1, [], [EOS_IDX], [], 0])
    data.sort(key = lambda x: len(x[2]), reverse = True)
    batch_len = len(data[0][2])
    batch = LongTensor([x[2] + [PAD_IDX] * (batch_len - len(x[2])) for x in data])
    mask = maskset(batch)
    enc_out = enc(batch, mask)
    dec_in = LongTensor([SOS_IDX] * BATCH_SIZE).unsqueeze(1)
    dec.hidden = enc.hidden
    if dec.feed_input:
        dec.attn.hidden = zeros(BATCH_SIZE, 1, HIDDEN_SIZE)
    heatmap = [[[""] + x[1] + [EOS]] for x in data[:len(eos)]] if VERBOSE else None
    while sum(eos) < len(eos) and t < MAX_LEN:
        dec_out = dec(dec_in, enc_out, t, mask)
        if BEAM_SIZE == 1:
            dec_in = greedy_search(dec, tgt_vocab, data, eos, dec_out, heatmap)
        else:
            dec_in = beam_search(dec, tgt_vocab, data, t, eos, dec_out, heatmap)
        t += 1
    if VERBOSE:
        for m in heatmap:
            print(mat2csv(m, rh = True))
    return [(x[1], [tgt_vocab[x] for x in x[3][:-1]]) for x in sorted(data[:len(eos)])]

def predict():
    idx = 0
    data = []
    result = []
    enc, dec, src_vocab, tgt_vocab = load_model()
    fo = open(sys.argv[4])
    for line in fo:
        tkn = tokenize(line, UNIT)
        x = [src_vocab[i] if i in src_vocab else UNK_IDX for i in tkn] + [EOS_IDX]
        data.extend([[idx, tkn, x, [], 0] for _ in range(BEAM_SIZE)])
        if len(data) == BATCH_SIZE:
            result.extend(run_model(enc, dec, tgt_vocab, data))
            data = []
        idx += 1
    fo.close()
    if len(data):
        result.extend(run_model(enc, dec, tgt_vocab, data))
    for x in result:
        print(x)

if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit("Usage: %s model vocab.src vocab.tgt test_data" % sys.argv[0])
    print("cuda: %s" % CUDA)
    print("batch size: %d" % BATCH_SIZE)
    with torch.no_grad():
        predict()
