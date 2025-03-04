import sys, csv

try:
	psl = open(sys.argv[1])
	isbed = sys.argv[1][-3:].lower() != 'psl' 
	gtf = open(sys.argv[2])
	outfilename = sys.argv[3]
	if len(sys.argv) > 4:
		proportion_annotated_covered = float(sys.argv[4])
	else:
		proportion_annotated_covered = 0.8
except:
	sys.stderr.write('usage: script.py psl/bed annotation.gtf renamed.psl/bed [proportion] \n')
	sys.stderr.write('purpose: changes the name for each entry in psl/bed to the isoform and gene\n')
	sys.stderr.write('optional argument: proportion should be a decimal < 1 specifying the % of an' +
		'annotated single-exon gene a FLAIR isoform has to cover (default=0.8)\n')
	sys.exit(1)

def get_junctions(line):
	junctions = set()
	starts = [int(n) + 1 for n in line[20].split(',')[:-1]]
	sizes = [int(n) - 1 for n in line[18].split(',')[:-1]]  # for indexing pupropses
	if len(starts) == 1:
		return
	for b in range(len(starts)-1): # block
		junctions.add((starts[b]+sizes[b], starts[b+1]))
	return junctions

def get_junctions_bed12(line):
	junctions = set()
	chrstart = int(line[1])
	starts = [int(n) + chrstart + 1 for n in line[11].split(',')[:-1]]
	sizes = [int(n) - 1 for n in line[10].split(',')[:-1]]
	if len(starts) == 1:
		return
	for b in range(len(starts)-1): # block
		junctions.add((starts[b]+sizes[b], starts[b+1]))
	return junctions

def bin_search(query, data):
	""" Query is a coordinate interval. Binary search for the query in sorted data, 
	which is a list of coordinates. Finishes when an overlapping value of query and 
	data exists and returns the index in data. """
	i = int(round(len(data)/2))  # binary search prep
	lower, upper = 0, len(data)
	while True:
		if upper - lower < 2:  # stop condition but not necessarily found
			break
		if data[i][1] < query[0]:
			lower = i
			i = int(round((i + upper)/2))
		elif data[i][0] > query[1]:
			upper = i
			i = int(round((lower + i)/2))
		else:  # found
			break
	return i

def overlapping_bases(coords0, coords1):
	""" complete coverage of coords0 by coords1, and coords0 can be tol larger.
	if coords0 is contained by coords1, then return the number of 
	overlapping basepairs """
	if coords0[1] > coords1[0] and coords1[1] > coords0[0]:
		return min(coords1[1], coords0[1]) - max(coords1[0], coords0[0])
	return

def update_tn_dicts(chrom, junctions, prev_transcript, prev_exon, junc_to_tn, \
	tn_to_juncs, all_se):
	if chrom not in junc_to_tn:
		junc_to_tn[chrom] = {}
		tn_to_juncs[chrom] = {}
		all_se[chrom] = []
	if not junctions:
		all_se[chrom] += [prev_exon]
	else:
		tn_to_juncs[chrom][prev_transcript] = junctions
		for j in junctions:
			if j not in junc_to_tn[chrom]:
				junc_to_tn[chrom][j] = set()
			junc_to_tn[chrom][j].add(prev_transcript)
	return junc_to_tn, tn_to_juncs, all_se

def update_gene_dicts(chrom, j, gene, junctions, gene_unique_juncs, junc_to_gene):
	junctions.add(j)
	if prev_gene not in gene_unique_juncs:
		gene_unique_juncs[prev_gene] = set()
	gene_unique_juncs[gene].add(j)
	if j not in junc_to_gene[chrom]:
		junc_to_gene[chrom][j] = set()
	junc_to_gene[chrom][j].add(gene)
	return junctions, gene_unique_juncs, junc_to_gene

prev_transcript, prev_exon = '', ''
junc_to_tn = {}  # matches intron to transcript; chrom: {intron: [transcripts], ... }
tn_to_juncs = {}  # matches transcript to intron; i.e. chrom: {transcript_name: (junction1, junction2), ... }
all_se = {}  # all single exon genes
junc_to_gene = {}  # matches a splice junction (i.e. an intron) to gene name
gene_unique_juncs = {}  # matches a gene to its set of unique splice junctions

for line in gtf:  # extract all exons from the gtf, keep exons grouped by transcript
	if line.startswith('#'):
		continue
	line = line.rstrip().split('\t')
	chrom, ty, start, end, strand = line[0], line[2], int(line[3]), int(line[4]), line[6]
	if ty != 'exon':
		continue
	this_transcript = line[8][line[8].find('transcript_id')+15:]
	this_transcript = this_transcript[:this_transcript.find('"')]

	if chrom not in junc_to_gene:
		junc_to_gene[chrom] = {}

	if this_transcript != prev_transcript:
		if prev_transcript:
			junc_to_tn, tn_to_juncs, all_se = update_tn_dicts(chrom, junctions, \
				prev_transcript, prev_exon, junc_to_tn, tn_to_juncs, all_se)
		junctions = set()
		prev_transcript = this_transcript
	elif strand == '-' and end < prev_start:
		junctions, gene_unique_juncs, junc_to_gene = update_gene_dicts(chrom, \
			(end, prev_start), prev_gene, junctions, gene_unique_juncs, junc_to_gene)
	else:
		junctions, gene_unique_juncs, junc_to_gene = update_gene_dicts(chrom, \
			(prev_end, start), prev_gene, junctions, gene_unique_juncs, junc_to_gene)

	prev_start, prev_end = start, end
	prev_gene = line[8][line[8].find('gene_id')+9:]
	prev_gene = prev_gene[:prev_gene.find('"')]
	prev_exon = (start, end, prev_gene)

if ty == 'exon' and prev_transcript:
	junc_to_tn, tn_to_juncs, all_se = update_tn_dicts(chrom, junctions, prev_transcript, \
		prev_exon, junc_to_tn, tn_to_juncs, all_se)

for chrom in all_se:
	all_se[chrom] = sorted(list(all_se[chrom]), key=lambda x: x[0])

name_counts = {}  # to avoid redundant names
with open(outfilename, 'wt') as outfile:
	writer = csv.writer(outfile, delimiter='\t')
	for line in psl:
		line = line.rstrip().split('\t')
		if isbed:
			junctions = get_junctions_bed12(line)
			chrom, name, start, end = line[0], line[3], int(line[1]), int(line[2])
		else:
			junctions = get_junctions(line)
			chrom, name, start, end = line[13], line[9], int(line[15]), int(line[16])

		if chrom not in junc_to_tn:  # chrom not in reference file
			if ';' in name:
				name = name[:name.find(';')]
			if name not in name_counts:
				name_counts[name] = 0
			else:
				name_counts[name] += 1
				name = name + '-' + str(name_counts[name])

			newname = name + '_noReference'
			if isbed:
				line[3] = newname
			else:
				line[9] = newname
			writer.writerow(line)
			continue

		gene_hits = {}
		if not junctions:
			exon = (start, end)
			i = bin_search(exon, all_se[chrom])
			first = True
			for e in all_se[chrom][i-2:i+2]:
				overlap = overlapping_bases(exon, e)
				if overlap:
					proportion = float(overlap)/(exon[1]-exon[0])  # base coverage of long-read isoform by the annotated isoform
					proportion2 = float(overlap)/(e[1]-e[0])  # base coverage of the annotated isoform by the long-read isoform
					if proportion > 0.5 and proportion2 > proportion_annotated_covered:
						gene_hits[e[2]] = proportion
		else:
			for j in junctions:
				if j in junc_to_gene[chrom]:
					for gene in junc_to_gene[chrom][j]:
						if gene not in gene_hits:
							gene_hits[gene] = 0
						gene_hits[gene] += 1  # gene name, number of junctions this isoform shares with this gene

		if not gene_hits:  # gene name will just be a chromosome locus
			gene = chrom + ':' + str(start)[:-3] + '000'
		else:  # gene name will be whichever gene the entry has more shared junctions with
			genes = sorted(gene_hits.items(), key=lambda x: x[1])  # sort by number of junctions shared with gene
			if len(genes) > 1 and len(genes) > 1 and genes[-1][1] == genes[-2][1]: # tie, break by gene size 
				genes = sorted(genes, key=lambda x: x[0])
				genes = sorted(genes, key=lambda x: x[1])
				g = genes[-1], len(gene_unique_juncs[genes[-1][0]])
				for i in reversed(range(len(genes)-1)):
					if genes[i][1] == g[0][1]:
						if len(gene_unique_juncs[genes[i][0]]) < g[1]:
							g = genes[i], len(gene_unique_juncs[genes[i][0]])
					else:
						break
				genes[-1] = g[0]
			gene = genes[-1][0]

		transcript = ''
		if junctions:
			matches = set()
			for j in junctions:
				if j in junc_to_tn[chrom]:
					matches.update(junc_to_tn[chrom][j])
			for t in sorted(list(matches)):
				if tn_to_juncs[chrom][t] == junctions:
					transcript = t  # annotated transcript identified
					break

		if not transcript:
			if ';' in name:
				name = name[:name.find(';')]
		else:
			name = transcript

		if name not in name_counts:
			name_counts[name] = 0
			newname = name + '_' + gene
		else:
			name_counts[name] += 1
			newname = name + '-' + str(name_counts[name]) + '_' + gene

		if isbed:
			line[3] = newname
		else:
			line[9] = newname
		writer.writerow(line)
