
### This program is a modified version of Wessim (originally developed from GemSim).

import sys
import random
import bisect
import gzip
import cPickle
import numpy
import argparse
import math
from time import time, localtime, strftime
import os

inds={'A':0,'T':1,'G':2,'C':3,'N':4,'a':0,'t':1,'g':2,'c':3,'n':4}

def main(argv):
    t0 = time()
    parser = argparse.ArgumentParser(description='sub-wessim: a sub-program for w-Wessim. (NOTE!) Do not run this program. Use "w-Wessim.py" instead. ', prog='w-Wessim-sub', formatter_class=argparse.RawTextHelpFormatter)
    group1 = parser.add_argument_group('Mandatory input files')
    group1.add_argument('-R', metavar = 'FILE', dest='reference', required=True, help='faidx-indexed (R)eference genome FASTA file')
    group1.add_argument('-P', metavar = 'FILE', dest='probe', required=True, help='(P)robe sequence FASTA file')
    group1.add_argument('-B', metavar = 'FILE', dest='probeblat', required=True, help='(B)lat matched probe regions .PSL file')
    group1.add_argument('--mvnfile', type=str, help="Path to mvntable", required=True)

    group2 = parser.add_argument_group('Parameters for exome capture')
    group2.add_argument('-f', metavar = 'INT', type=int, dest='fragsize', required=False, help='mean (f)ragment size, corresponding to insert size between paired ends. [200]', default=200)
    group2.add_argument('-d', metavar = 'INT', type=int, dest='fragsd', required=False, help='standard (d)eviation of fragment size [50]', default=50)
    group2.add_argument('-m', metavar = 'INT', type=int, dest='fragmin', required=False, help='(m)inimum fragment length [read_length + 20]')
    group2.add_argument('-y', metavar = 'PERCENT',type=int, dest='bind', required=False, help='minimum required fraction of probe match to be h(y)bridized [50]', default=50)
    group2.add_argument('-w', metavar = 'INT', type=int, dest='weight', required=False, help='penalty (w)eight for indel in the hybridization [2]', default=2)

    group3 = parser.add_argument_group('Parameters for sequencing')
    group3.add_argument('-n', metavar = 'INT', type=int, dest='readnumber', required=True, help='total (n)umber of reads\read pairs')
    group3.add_argument('-l', metavar = 'INTord', dest='readlength', required=True, help='read (l)ength (bp)')
    group3.add_argument('-M', metavar = 'FILE', dest='model', required=True, help='GemSim (M)odel file (.gzip)')

    group4 = parser.add_argument_group('Output options')
    group4.add_argument('-o', metavar = 'FILE', dest='outfile', help='(o)utput file header. ".fastq.gz" or ".fastq" will be attached automatically. Output will be splitted into two files', required=True)
    group4.add_argument('-z', action='store_true', help='compress output with g(z)ip [false]')
    group4.add_argument('-q', metavar = 'INT', type=int, dest='qualbase', required=False, help='(q)uality score offset [33]', default=33)

    args = parser.parse_args()
    reffile = args.reference
    fref = None
    frefs = []
    metap = []
    metamode = False
    probefile = args.probe
    alignfile = args.probeblat

    isize = args.fragsize
    isd = args.fragsd
    imin = args.fragmin
    bind = args.bind
    weight = args.weight

    readlength = args.readlength
    readnumber = args.readnumber

    if imin==None:
        imin = int(readlength) + 20
    if isize < imin:
        print "too small mean fragment size (" + str(isize) + ") compared to minimum length (" + str(imin) + "). Increase it and try again."
        sys.exit(0)
    model = args.model

    outfile = args.outfile
    compress = args.z
    qualbase = args.qualbase

    print
    print "-------------------------------------------"
    print "Reference:", reffile
    print "Probeset:", probefile
    print "Probematch:", alignfile
    print "Fragment:",isize, "+-", isd, ">", imin
    print "Sequencing model:", model
    print "Read length:", readlength, "Read number:", readnumber
    print "Output File:", outfile
    print "Gzip compress?", compress
    print "Quality base:", qualbase
    print "Job started at:", strftime("%Y-%m-%d %H:%M:%S", localtime())
    print "-------------------------------------------"
    print

    matchdic = {}
    countdic = {}
    referencedict={}
    reflist=[]

    #read in reference file into dictionary
    chromo=''
    with open(reffile,'r') as reffi:
        for l in reffi:
            if l.startswith('>'):
                if chromo!='': referencedict[chromo]=''.join(reflist)
                reflist=[]
                chromo=l.strip().split(" ")[0][1:]
                referencedict[l.strip().split(" ")[0]]=''
            else:
                reflist.append(l.strip())
    referencedict[chromo]=''.join(reflist)
    reflist=''

    #open output files
    wread = None
    wread2 = None
    if compress:
        wread = gzip.open(outfile + "_1.fastq.gz", 'wb')
        wread2 = gzip.open(outfile + "_2.fastq.gz", 'wb')
    else:
        wread = open(outfile + "_1.fastq", 'w')
        wread2 = open(outfile + "_2.fastq", 'w')

    #Read in align and probe file
    with open(probefile, 'r') as f1:
        with open(alignfile, 'r') as f2:
            line1 = f1.readline()
            processed = 0
            totalseq = 1
            first = True
            dirtag = ('','+','-')
            for i in range(0, 5): ### Ignore first 5 lines of psl file (header)
                line2 = f2.readline()
            while line1:
                seqid = line1.strip()[1:]
                values = line2.split("\t")
                if len(values)<17:
                    line1 = f1.readline()
                    line1 = f1.readline()
                    first = True
                    totalseq += 1
                    continue
                qgapcount = int(values[4])
                qgapsize = int(values[5])
                tgapcount = int(values[6])
                tgapsize = int(values[7])
                pslid = values[9]
                pslscore = int(values[0])
                pslchrom = values[13]
                pslstart = values[15]
                pslend= values[16]
                if qgapcount!=0 or tgapcount!=0:
                    pslscore = pslscore - qgapcount * (weight - 1) - tgapcount * (weight - 1)
                if qgapsize > 2 or tgapsize > 2:
                    line2 = f2.readline()
                    continue
                if not seqid==pslid:
                    line1 = f1.readline()
                    line1 = f1.readline()
                    processed+=1
                    totalseq += 1
                    first = True
                    continue
                if not first:
                    matchdic[seqid].append((pslscore, pslchrom, int(pslstart), int(pslend)))
                else:
                    matchdic[seqid] = [(pslscore, pslchrom, int(pslstart), int(pslend))]
                    first = False
                line2 = f2.readline()
    matchkeys = matchdic.keys()

    #count number of matches for each probe
    matchweights={}
    for seq in matchdic:
        if type(matchdic[seq][0])==int:
            n=1
        else:
            n=len(matchdic[seq])
        matchweights[seq]=n
    sequences=[k for k in matchweights for x in range(matchweights[k])]

    #Parse model
    mx1,mx2,insD1,insD2,delD1,delD2,intervals,gQualL,bQualL,iQualL,mates,rds,rdLenD = parseModel(model, readlength)
    m0=float(mates[0])
    m1=float(mates[1])
    rd0=float(rds[0])
    rd1=float(rds[1])
    unAlign0=(m0*rd1-m1*m0)/(rd0*rd1-m1*m0)
    unAlign1=1.0-(unAlign0/(m0/rd0))
    keys=intervals.keys()
    keys.sort()
    if isize=='emp':
        inters=[]
        for k in keys:
            inters.append((k,intervals[k]))
        interval=bisect_choiceTUP(inters)
    #inserts1and2
    insDict1=mkInserts(mx1,insD1)
    insDict2=mkInserts(mx2,insD2)
    #deletions1and2
    delDict1=mkDels(mx1,delD1)
    delDict2=mkDels(mx2,delD2)
    gens=genRef('')
    gQList=[]
    for i in (gQualL):
        gL=[]
        keys=i.keys()
        keys.sort()
        for k in keys:
            gL.append((chr(k+qualbase),i[k]))
        gQList.append(bisect_choiceTUP(gL))
    #choose bad quality bases
    bQList=[]
    for i in (bQualL):
        bL=[]
        keys=i.keys()
        keys.sort()
        for k in keys:
            bL.append((chr(k+qualbase),i[k]))
        bQList.append(bisect_choiceTUP(bL))
    #choose qualities for inserts
    iQList=[]
    for i in (iQualL):
        iL=[]
        keys=i.keys()
        keys.sort()
        for k in keys:
            iL.append((chr(k+qualbase),i[k]))
        iQList.append(bisect_choiceTUP(iL))
    #choose read length
    if readlength=='d':
        print('Using empirical read length distribution')
        lgth=[]
        keys=rdLenD.keys()
        keys.sort()
        for k in keys:
            lgth.append((k,rdLenD[k]))
        RL=bisect_choiceTUP(lgth)
    else:
        RL=ln(readlength)

    mvnTable = readmvnTable(args.mvnfile)
    gcVector = getFragmentUniform(referencedict, matchkeys, matchdic, isize, 1000, bind,sequences)
    gcSD = numpy.std(gcVector)
    newSD = isd*2

    ### Generate!
    count = 0
    i = 1
    seq = ""
    seqgenome = "g1"
    while i < readnumber+1:
        key = pickonekey(sequences)
        fragment = getFragment(matchdic, key, isize, newSD, imin, bind)
        fragment_chrom = fragment[0]
        fragment_start = int(fragment[1])
        fragment_end = int(fragment[2])
        if fragment_start < 0:
            continue
        seq = getSequence(referencedict, fragment)
        if len(seq)<imin:
            continue
        gccount = getGCCount(seq)
        keep = H2(len(seq), gccount, isize, newSD, isd, gcSD,mvnTable)
        if not keep:
            continue
        ref = seq
        refLen=len(ref)
        val=random.random()
        ln1=RL()
        ln2=RL()
        inter = isize
        read1,pos1,dir1,quals1,read2,pos2,dir2,quals2 = readGenp(ref,refLen,ln1,ln2,gens(),mx1,insDict1,delDict1,gQList,bQList,iQList,qualbase)
        p1 = fragment_chrom + "_" + str(fragment_start + pos1 + 1) + "_" + dirtag[dir1]
        p2 = fragment_chrom + "_" + str(fragment_start + pos2 + 1) + "_" + dirtag[dir2]
        if val > unAlign0+unAlign1:
            pass
        elif val > unAlign1:
            read2='N'*ln2
            quals2=chr(0+qualbase)*ln2
            p2 = '*'
        else:
            read1='N'*ln1
            quals1=chr(0+qualbase)*ln1
            p1='*'
        head1='@'+'r'+str(i)+'_from_'+ seqgenome + ";" + p1 + ":" + p2 + "/1"
        head2='@'+'r'+str(i)+'_from_'+ seqgenome + ";" + p1 + ":" + p2 + "/2"
        wread.write(head1 + '\n')
        wread.write(read1.upper()+'\n')
        wread.write('+\n')
        wread.write(quals1+'\n')
        wread2.write(head2 + "\n")
        wread2.write(read2.upper() + "\n")
        wread2.write("+\n")
        wread2.write(quals2 + "\n")
        count +=1
        i+=1
        if count % 1000000 == 0 and count!=0:
            t1 = time()
            print str(count) + " reads have been generated... in %f secs" % (t1-t0)
    wread.close()
    wread2.close()
    t1 = time()
    print "Done generating " + str(readnumber) + " reads in %f secs" % (t1 - t0)

def pickonekey(sequences):
	key = random.choice(sequences)
	return key

def getSequence(referencedict, fragment):
	chrom = fragment[0]
	start = int(fragment[1])
	end = int(fragment[2])
	seq = referencedict[chrom][start:end]
	return seq

def getFragment(matchdic, key, mu, sigma, lower, bind):
	ins = getInsertLength(mu, sigma, lower)
	match = matchdic[key]
	pickedproberegion = pickproberegion(match)
	pickedfragment = pickFragment(pickedproberegion, ins, bind)
	return pickedfragment

def getFragmentUniform(referencedict, matchkeys, matchdic, mu, total, bind,sequences):########################################################################################################
	result = []
	ins = mu
	i = 0
	seq = ""
	while i < 1000:
		key = pickonekey(sequences)
		match = matchdic[key]
		pickedproberegion = pickproberegion(match)
		pickedfragment = pickFragment(pickedproberegion, ins, bind)
		fragment_chrom = pickedfragment[0]
		fragment_start = int(pickedfragment[1])
		fragment_end = int(pickedfragment[2])
		if fragment_start < 0:
			continue
		seq = getSequence(referencedict, pickedfragment)
		if len(seq)<ins:
			continue
		gcCount = getGCCount(seq)
		result.append(gcCount)
		i+=1
	return result

def getInsertLength(mu, sigma, lower):
	while True:
		length = int(random.gauss(mu, sigma))
		if length >= lower:
			return length

def pickproberegion(match):
	scores = []
	for m in match:
		scores.append(int(m[0]))
	reprobs_cumul = scoretoprob(scores, 0.7)
	ran = random.random()
	ind = bisect.bisect_left(reprobs_cumul, ran)
	pickedmatch = match[ind]
	return pickedmatch

def pickFragment(pickedproberegion, ins, bind):
	probechrom = pickedproberegion[1]
	probestart = int(pickedproberegion[2])
	probeend = int(pickedproberegion[3])
	probelength = probeend - probestart
	minimummatch = int(probelength*bind/100)
	overlap = int(random.triangular(minimummatch, probelength, probelength))
	margin = max(ins - overlap, 0)
	rangestart = probestart - margin
	rangeend = probeend + margin
	seqstart = random.randint(rangestart, rangeend - ins)
	return probechrom, seqstart, seqstart + ins

def scoretoprob(scores, r):
	maxscore = max(scores)
	rescores = []
	reprobs = []
	reprobs_cumul = []
	totalscore = 0.0
	for score in scores:
		mismatch = maxscore - score
		rescore = 1.0 * pow(r, mismatch)
		rescores.append(rescore)
		totalscore += rescore
	totalprob = 0.0
	for rescore in rescores:
		reprob = rescore / totalscore
		totalprob += reprob
		reprobs.append(reprob)
		reprobs_cumul.append(totalprob)
	return reprobs_cumul

def getGCCount(seq):
	gc = 0
	for nuc in seq:
		if nuc=="G" or nuc=="C" or nuc=="g" or nuc=="c":
			gc += 1
	return gc

def comp(sequence):
	""" complements a sequence, preserving case. Function imported from GemSim"""
	d={'A':'T','T':'A','C':'G','G':'C','a':'t','t':'a','c':'g','g':'c','N':'N','n':'n'}
	cSeq=''
	for s in sequence:
		if s in d.keys():
			cSeq+=d[s]
		else:
			cSeq+='N'
	return cSeq

def usage():
	print ">python x3.probestatistics reference.fa probe.fa probealign.psl readoutput.fastq.gz"
	sys.exit()

def test(filename):
	mx1,mx2,insD1,insD2,delD1,delD2,intervals,gQualL,bQualL,iQualL,mates,rds,rdLenD = parseModel(filename, 100)
	sys.exit(1)

def parseModel(gzipFile,readlen):
	"""prepares error models for input to mkErrors."""
	file=gzip.open(gzipFile,'rb')
	modReadLen=cPickle.load(file)
	if readlen!='d' and readlen>modReadLen:
		print "Inappropriate read length chosen for model. Maximum for this model: " + str(modReadLen)
		file.close()
		sys.exit()
	mx1=cPickle.load(file)
	mx2=cPickle.load(file)
	insD1=cPickle.load(file)
	insD2=cPickle.load(file)
	delD1=cPickle.load(file)
	delD2=cPickle.load(file)
	intD=cPickle.load(file)
	gQualL=cPickle.load(file)
	bQualL=cPickle.load(file)
	iQualL=cPickle.load(file)
	mates=cPickle.load(file)
	rds=cPickle.load(file)
	rdLenD=cPickle.load(file)
	file.close()
	return mx1,mx2,insD1,insD2,delD1,delD2,intD,gQualL,bQualL,iQualL,mates,rds,rdLenD

def mkInserts(mx,insD):
	"""Returns a dictionary consisting of compiled functions to make inserts."""
	insertDict={}
	posKeys=insD.keys()
	posKeys.sort()
	for p in posKeys:
		indicies=p.split('.')
		tot=mx[int(indicies[0])][int(indicies[1])][int(indicies[2])][int(indicies[3])][int(indicies[4])][int(indicies[5])][5]
		insertKeys=insD[p].keys()
		insertKeys.sort()
		insertList=[]
		iSum=0
		for i in insertKeys:
			insertList.append((i,insD[p][i]))
			iSum+=0
		insertList.append(('',tot-iSum))
		insert=bisect_choiceTUP(insertList)
		insertDict[p]=insert
	return insertDict

def mkDels(mx,delD):
	"""Returns a dictionary consisting of compiled functions to make deletiosn."""
	deletionDict={}
	posKeys=delD.keys()
	posKeys.sort()
	for p in posKeys:
		indicies=p.split('.')
		tot=mx[int(indicies[0])][int(indicies[1])][int(indicies[2])][int(indicies[3])][int(indicies[4])][int(indicies[5])][5]
		items=delD[p]
		items.reverse()
		items.append(tot-sum(items))
		items.reverse()
		delete=bisect_choice(items)
		deletionDict[p]=delete
	return deletionDict

def bisect_choice(items):
	"""Returns a function that makes a weighted random choice from items."""
	added_weights = []
	last_sum = 0
	for weight in items:
		last_sum += weight
		added_weights.append(last_sum)
	def choice(rnd=random.random, bis=bisect.bisect):
		return bis(added_weights, rnd() * last_sum)
	return choice

def bisect_choiceTUP(items):
	"""Returns a function that makes a weighted random choice from a list of tuples."""
	added_weights = []
	last_sum = 0.0
	for item,weight in items:
		weight=float(weight)
		last_sum += weight
		added_weights.append(last_sum)
	def choice(rnd=random.random, bis=bisect.bisect):
		return items[bis(added_weights, rnd() * last_sum)][0]
	return choice

def ln(length):
	"""Returns static length as a funtion."""
	def val():
		return length
	return val

def readGenp(ref, refLen, readLen1, readLen2, genos, mx1, insD1, delD1, gQ, bQ, iQ, qual):
	"""Generates a pair of reads from given DNA fragment."""
	cRef = comp(ref)[::-1]
	extrabase = 10
	ind1 = 0
	ind2 = refLen - readLen2
	end1 = readLen1 + extrabase
	end2 = ind2 + readLen2
	dir1=1
	dir2=2
	read1 = ref[ind1:end1]
	read2 = cRef[ind1:end1]
	read1, quals1 = mkErrors(read1, readLen1, mx1, insD1, delD1, gQ, bQ, iQ, qual)
	read2, quals2 = mkErrors(read2, readLen2, mx1, insD1, delD1, gQ, bQ, iQ, qual)
	pairorder = random.randint(1,2)
	if pairorder==1:
		return read1, ind1, dir1, quals1, read2, ind2, dir2, quals2
	else:
		return read2, ind2, dir2, quals2, read1, ind1, dir1, quals1

def mutate(read,ind,gens,refLen,dir,readLn,hd):
	"""Adds predetermined mutations to reads."""
	d={'A':'T','T':'A','C':'G','G':'C','a':'t','t':'a','c':'g','g':'c','N':'N','n':'n'}
	if gens=={}:
		return read
	else:
		chroms=gens.keys()
		if hd not in chroms:
			return read
		else:
			posi=gens[hd].keys()
			if dir==1:
				for p in posi:
					if p >ind and p<=(ind+readLn):
						read1=read[:p-(ind+1)]+gens[hd][p]
						read1=read1+read[p-ind:]
						read=read1
					elif p<=ind+readLn-refLen:
						read1=read[:refLen-ind+p-1]+gens[hd][p]
						read1+=read[refLen-ind+p:]
						read=read1
				return read
			elif dir==2:
				for p in posi:
					if p >ind and p<=(ind+readLn):
						read1=read[:p-(ind+1)]+d[gens[hd][p]]
						read1=read1+read[p-ind:]
						read=read1
					elif p<=ind+readLn-refLen:
						read1=read[:refLen-ind+p-1]+d[gens[hd][p]]
						read1+=read[refLen-ind+p:]
						read=read1
				return read

def genRef(ref):
	"""Returns input as function"""
	def r():
		return ref
	return r

def mkErrors(read,readLen,mx,insD,delD,gQ,bQ,iQ,qual):
	"""Adds random errors to read."""
	pos=0
	quals=''
	qualslist = []
	index='0.4.4.4.4.'+str(inds[read[0]])
	if index in insD:
		insert=insD[index]()
		read='NNNN'+insert+read
		for i in insert:
#			quals+=iQ[0]()
			qualslist.append(iQ[0]())
			pos+=1
	else:
		read='NNNN'+read
	prev=read[pos:pos+4]
	after = read[pos+4]
	d0=pos
	d1=inds[prev[3]]
	d2=inds[prev[2]]
	d3=inds[prev[1]]
	d4=inds[prev[0]]
	d5=inds[after]
	pos+=1
	while pos<=readLen and pos<len(read)-4:
		deleted='no' #GT
		d0 = pos
		d4 = d3
		d3 = d2
		d2 = d1
		d1 = d5
		d5 = inds[read[pos+4]]
		index = '.'.join([str(d0), str(d1), str(d2), str(d3), str(d4), str(d5)])
		Mprobs=mx[d0][d1][d2][d3][d4][d5]
		tot=float(Mprobs[5])
		if not tot==0:
			Mprobs = Mprobs/tot
		val=random.random()
		a=Mprobs[0]
		t=Mprobs[1]+a
		g=Mprobs[2]+t
		c=Mprobs[3]+g
		n=Mprobs[4]+c
		success=False
		if val>n or tot == 0:
			gPos=pos-1
			while gPos>=0:
				try:
					qualslist.append(gQ[gPos]())
					success=True
					break
				except:
					gPos-=1
			if success==False:
				qualslist.append(chr(30+qual))
		elif val>c:
			read=read[:pos+3]+'N'+read[pos+4:]
			bPos=pos-1
			while bPos>=0:
				try:
					qualslist.append(bQ[bPos]())
					success=True
					break
				except:
					bPos-1
				if success==False:
					qualslist.append(chr(2+qual))
		elif val>g:
			read=read[:pos+3]+'C'+read[pos+4:]
			bPos=pos-1
			while bPos>=0:
				try:
					qualslist.append(bQ[bPos]())
					success=True
					break
				except:
					bPos-1
				if success==False:
					qualslist.append(chr(2+qual))
		elif val>t:
			read=read[:pos+3]+'G'+read[pos+4:]
			bPos=pos-1
			while bPos>=0:
				try:
					qualslist.append(bQ[bPos]())
					success=True
					break
				except:
					bPos-1
				if success==False:
					qualslist.append(chr(2+qual))
		elif val>a:
			read=read[:pos+3]+'T'+read[pos+4:]
			bPos=pos-1
			while bPos>=0:
				try:
					qualslist.append(bQ[bPos]())
					success=True
					break
				except:
					bPos-1
				if success==False:
					qualslist.append(chr(2+qual))
		else:
			read=read[:pos+3]+'A'+read[pos+4:]
			bPos=pos-1
			while bPos>=0:
				try:
					qualslist.append(bQ[bPos]())
					success=True
					break
				except:
					bPos-1
				if success==False:
					qualslist.append(chr(2+qual))
		if index in delD:
			delete=delD[index]()
			read=read[:pos+4]+read[pos+delete+4:]
			if delete>0: #GT
				deleted='yes' #GT
		if index in insD:
			insert=insD[index]()
			read=read[:pos+4]+insert+read[pos+4:]
			for i in insert:
				iPos=pos-1
				while iPos>=0:
					try:
						qualslist.append(iQ[iPos]())
						success=True
						break
					except:
						iPos-=1
					if success==False:
						qualslist.append(chr(2+qual))
			pos+=len(insert)
		pos+=1
	if deleted=='no' or pos==len(read)-4: #GT
		qualslist.append(qualslist[-1]) #GT
	readback = read
	read=read[4:readLen+4]
	quals=''.join(qualslist)[:readLen]
	if len(quals)!=len(read):
		print "unexpected stop"
		return None, None
	return read,quals

def generateM(sd, newSD, x,t, gcVector):
	gcSD = numpy.std(gcVector)*(newSD/sd)
	s00 = gcSD*gcSD + newSD*newSD*t*t
	s11 = newSD*newSD
	rho = newSD*t/math.sqrt(s00)
	m = numpy.matrix([[s00, rho*math.sqrt(s00*s11)], [rho*math.sqrt(s00*s11), s11]])
	w, v = numpy.linalg.eig(m)
	d = numpy.matrix([[math.sqrt(w[0]),0],[0,math.sqrt(w[1])]])
	M = v*d
	return M, m

def generateMatrices(sd,x, gcVector):
	M1, m1 = generateM(sd, sd, x,1/0.9, gcVector)
	e1 = numpy.matrix([[1],[0]])
	e2 = numpy.matrix([[0],[1]])
	longAxis1 = M1*e1
	longAxis2 = M1*e2
	longAxis = longAxis1
	if norm(longAxis1) < norm(longAxis2):
		longAxis = longAxis2
	M2 = []
	m2 = []
	newSD = sd;
	for i in range(100, 1000):
		newSD = sd*i/100.0
		M2, m2= generateM(sd, newSD,x,0.5, gcVector)
		if norm(numpy.linalg.inv(M2)*longAxis)<1.0:
			break
	u1 = numpy.linalg.inv(M1)
	u2 = numpy.linalg.inv(M2)
	return u1, u2, newSD, m1, m2

def getProb(l,n,x,sd,gcSD,alpha, mvnpdf):
	p1 = mvnpdf[0][int(cut((l-x)/sd)*100)]
	p2 = mvnpdf[0][int(cut((n-(x/2+(l-x)*alpha))/(l*gcSD/x))*100)]
	return float(p1)*float(p2)


def H2(l, n, x, sd1, sd2, gcSD, mvnpdf):
	bp = getProb(l,n,x,sd1,gcSD,.5,mvnpdf)
	ap = getProb(l,n,x,sd2,gcSD,9/7,mvnpdf)
	v = ap/bp

	r = random.random()
	toKeep = v > r
	return toKeep


def norm(x):
	y=x[0]*x[0]+x[1]*x[1]
	return math.sqrt(y)

def cut(x):
	y = abs(x)
	if y >5.00:
		y = 5.00
	return y

def H(l, n, x, u1, u2, mvnpdf):
	u = numpy.matrix([[x/2], [x]])
	nl1 = numpy.matrix([[n],[l]])
	v1 = u1*(nl1-u)
	v2 = u2*(nl1-u)

	p1 = mvnpdf[int(cut(v1[0])*100)][int(cut(v1[1])*100)]
	p2 = mvnpdf[int(cut(v2[0])*100)][int(cut(v2[1])*100)]
	v = float(p1)/float(p2)

	r = random.random()
	toKeep = v > r
	return toKeep

def readmvnTable(mvn_path):
	f = open(mvn_path)
	context = f.read()
	lines = context.split("\n")
	mvnTable = []
	for line in lines:
		values = line.split("\t")
		if len(values)<500:
			continue
		mvnTable.append(values)
	f.close()
	return mvnTable

if __name__=="__main__":
	main(sys.argv[1:])
	sys.exit(0)
