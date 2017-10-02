#!/usr/bin/env python
import sys, os, glob, cPickle
import argparse
#import shutil
import gzip
import collections
import itertools
import subprocess
import operator
import pprint
import time
#import multiprocessing

import numpy as np
#import scipy.stats
#import matplotlib.pyplot as plt

#import file_IO
import streaming_convergence
import RBNS_utils
import RBNS_settings
import RBNS_cluster_utils
import RBNS_lib
#import RBNS_plots
#import RBNS_kmers_by_position
#import run_RBNS_logos
#import RBNS_folding
#import RBNS_fold_split_reads
#import RBNS_clustering
#import RBNS_logo_helpers
#import RBNS_transcriptome_kmers






class Bnse:
    def __init__( self,
            settings,
            counts_on_cluster = False,
            quick = False ):

        self.settings = settings
        self.counts_on_cluster = counts_on_cluster
        self.quick = quick
        self.split_reads()
        self.get_lib_complexity()
        self.do_counts()
        self.make_sure_counts_worked()
        self.initialize_libs()
        self.calculate_all_enrichments()
        if ( self.zeronM_lib != None ):
            self.calculate_all_enrichments_to_0nM()
        self.determine_most_enriched_lib()
        self.sort_all_kmers_by_enrichment()

        if ( quick == True ):
            return

        #### The nt frequencies by position in each library
        if (settings.get_property('nt_freqs_by_position') == True):
            self.get_nt_freqs_by_position()

        self.make_tables()



    ###########################################################################
    ###########################################################################
    ###########################################################################



    def split_reads( self,
            redo_split = False ):
        """
        - Splits all the reads
        """
        all_exist = True
        for lib_settings in self.settings.iter_lib_settings():
            #if not (lib_settings.split_reads_exist()) or \
            #        (not lib_settings.split_fastqs_exist()):
            if not (lib_settings.split_reads_exist()):
                all_exist = False
                break

        if all_exist and not redo_split:
            return

        total_reads = 0
        bad_barcodes = collections.Counter()
        reads_per_barcode = collections.Counter()
        barcodes = self.settings.get_property('barcodes')

        #### See if an adapter sequence was passed in to get reads
        ####    with the correct random insert length
        start_of_adapter_seq = self.settings.get_property('start_of_adapter_seq')
        if (start_of_adapter_seq != None):
            print "Checking for adapter sequences that match {}".format(
                    start_of_adapter_seq )
            check_for_perfect_adapter = True
            num_reads_by_barcode_randomlen_D = {}
            for barcode in barcodes:
                num_reads_by_barcode_randomlen_D[barcode] = {}

        else:
            check_for_perfect_adapter = False
            num_reads_by_barcode_randomlen_D = None


        read_len = self.settings.get_property('read_len')
        #### Make the split_reads directory
        RBNS_utils.make_dir( self.rdir_path('split_reads') )
        #### the handles for the .reads files
        barcode2of = self.get_all_barcode_handles()
        #### the handles for the .gzipped fastqs
        barcode2of_fastqs = self.get_all_barcode_fastq_handles()

        #### If the insert length can be checked for, get those handles
        if (check_for_perfect_adapter == True):
            barcode_wronginsertlen_2of = self.get_all_barcode_handles_wrong_insert_len()
        print "\nSplitting reads in: {}\n".format( self.settings.get_fastq() )
        print "\tto: {}\n".format( self.rdir_path('split_reads') )

        num_reads_by_barcode_numCG_D = {}
        for barcode in barcodes:
            num_reads_by_barcode_numCG_D[barcode] = {}
            for num_CG in range( read_len + 1 ):
                num_reads_by_barcode_numCG_D[barcode][num_CG] = 0

        for l1, l2, l3, l4 in RBNS_utils.iterNlines(self.settings.get_fastq(), 4):
            barcode = RBNS_utils.get_barcode(l1,
                    self.settings.get_property('begin_barcode_symb'),
                    self.settings.get_property('end_barcode_symb'))[0:self.settings.get_property('barcode_len')]
            barcode_match = self.get_barcode_match(barcode, barcodes)
            total_reads += 1
            #if ( total_reads == 100000 ):
            #    break
            if not barcode_match:
                bad_barcodes[barcode] += 1
                continue
            else:
                if (check_for_perfect_adapter == True):

                    nt_before_barcode = l2.strip().rfind( start_of_adapter_seq )
                    try:
                        num_reads_by_barcode_randomlen_D[barcode][nt_before_barcode] += 1
                    except KeyError:
                        num_reads_by_barcode_randomlen_D[barcode][nt_before_barcode] = 1
                    #### If the random region is equal to the expected
                    ####    read_len, write it out
                    if (nt_before_barcode == read_len):
                        trimmed_read = l2.strip()[:read_len]
                        trimmed_quality = l4.strip()[:read_len]
                        barcode2of[barcode_match].write(trimmed_read + '\n')
                        reads_per_barcode[barcode_match] += 1
                        # write all 4 lines to the fastq files
                        barcode2of_fastqs[barcode_match].write(
                            l1 + trimmed_read + '\n' + l3 + trimmed_quality + '\n')
                    else:
                        barcode_wronginsertlen_2of[barcode_match].write( l2 )

                else:

                    trimmed_read = l2.strip()[:read_len]
                    trimmed_quality = l4.strip()[:read_len]
                    barcode2of[barcode_match].write(trimmed_read + '\n')
                    reads_per_barcode[barcode_match] += 1
                    # write all 4 lines to the fastq files
                    barcode2of_fastqs[barcode_match].write(
                        l1 + trimmed_read + '\n' + l3 + trimmed_quality + '\n')

        print 'Done splitting reads.\n'
        self.write_barcode_log(
                reads_per_barcode,
                total_reads,
                bad_barcodes,
                num_reads_by_barcode_randomlen_D = num_reads_by_barcode_randomlen_D)
        # close all of the file handles
        map( lambda f: f.close(), barcode2of.values() )
        map( lambda f: f.close(), barcode2of_fastqs.values() )

        if check_for_perfect_adapter:
            map( lambda f: f.close(), barcode_wronginsertlen_2of.values() )


    def write_barcode_log(self,
            reads_per_barcode,
            total_reads,
            bad_barcodes,
            num_reads_by_barcode_randomlen_D = None):
        """
        - Writes the log of which other barcodes were present.
            - If num_reads_by_barcode_randomlen_D is passed in,
                will calculate the percentage of reads that have a random
                insert of each particular length (e.g., len 18, 19, 20, 21, 22)
        """
        barcode_log_of = self.get_rdir_fhandle('split_reads',
            '{}_barcode_log.txt'.format(
                self.settings.get_property( "protein_name" ).replace(" ", "_") ) )

        barcode_log_of.write( 'Barcode\tConc\tReads' )

        if (num_reads_by_barcode_randomlen_D != None):
            read_len = self.settings.get_property('read_len')
            #### Write out the random insert sizes +/- 2 from read_len
            barcode_log_of.write('\t\t')
            for length in range( -1, 41 ):
                barcode_log_of.write( '{}\t'.format( length ))
        barcode_log_of.write("\n")

        for barcode, conc in itertools.izip(
                    self.settings.get_property('barcodes'),
                    self.settings.get_property('concentrations')):
            barcode_log_of.write('%s\t%s\t%s' %
              (barcode,
              str(conc) if barcode != self.settings.get_property('input_barcode')
              else 'input library',
              "{:,}".format(reads_per_barcode[barcode])))
            #### Write out the % of reads at each random read length
            if (num_reads_by_barcode_randomlen_D != None):
                barcode_log_of.write('\t\t')
                for length in range( -1, 41 ):
                    perc_str = "0%"
                    try:
                        perc_this_len = num_reads_by_barcode_randomlen_D[barcode][length] *\
                                100./sum( num_reads_by_barcode_randomlen_D[barcode].values() )
                        perc_str = "{0:.2f}%".format( perc_this_len )
                    except KeyError:
                        pass
                    barcode_log_of.write( '{}\t'.format( perc_str ))
            barcode_log_of.write('\n')

        barcode_log_of.write('total_reads\t%s\nbad barcode\t%s\n\n'
                % ("{:,}".format(total_reads), "{:,}".format(sum(bad_barcodes.values()))))
        barcode_log_of.write('Bad Barcode Summary\n')
        for bad_barcode, count in sorted(
          bad_barcodes.items(), key=operator.itemgetter(1), reverse=True):
            barcode_log_of.write('%s\t%s\n' % (bad_barcode,
                "{:,}".format(int(count))))


    def get_lib_complexity( self ):
        """
        - Gets the library complexity
        """

        lib_complexity_F = os.path.join( self.rdir_path('split_reads'),
                "{0}.lib_complexity.txt".format(
                    self.settings.get_property( "protein_name" ).replace(" ", "_") ) )
        if os.path.exists( lib_complexity_F ):
            if self.settings.get_property('make_unique_reads_f'):
                all_unique_reads_exist = True
                unique_reads_DIR = self.rdir_path('unique/split_reads')
                for reads_F, annot in self.return_reads_F_annot_tuples_L_with_input_first():
                    unique_reads_F = os.path.join( unique_reads_DIR,
                            os.path.basename( reads_F ) )
                    if not os.path.exists( unique_reads_F ):
                        all_unique_reads_exist = False
                ##### If all of the unique .reads files already exist, return
                if all_unique_reads_exist:
                    return

            #### If unique .reads files are not to be made, return
            else:
                return

        times_present_S = set()
        annots_L = []
        line_by_count_Ds_by_annot_D = {}
        for reads_F, annot in self.return_reads_F_annot_tuples_L_with_input_first():

            annots_L.append( annot )

            returned_D = self.get_lib_complexity_of_reads_F(
                reads_F,
                make_unique_reads_F = self.settings.get_property('make_unique_reads_f') )

            line_by_count_D = returned_D["line_by_count_D"]
            line_by_count_Ds_by_annot_D[annot] = line_by_count_D

            for times_present in line_by_count_D:
                times_present_S.add( times_present )

        times_present_L = list( times_present_S )
        times_present_L.sort()

        with open( lib_complexity_F, 'w' ) as f:
            f.write( "{}\t".format( self.settings.get_property( "protein_name_for_plotting" ))\
                    + "\t".join( annots_L ) + "\n" )

            for times_present in times_present_L:
                f.write( "{}x:\t".format( times_present ) )
                for annot in annots_L:
                    try:
                        str_to_write = line_by_count_Ds_by_annot_D[annot][times_present]
                    except KeyError:
                        str_to_write = ""
                    f.write( "{}\t".format( str_to_write ) )
                f.write( "\n" )

    def get_lib_complexity_of_reads_F( self,
            reads_F,
            remove_sorted = True,
            make_unique_reads_F = True ):
        """
        - Gets the library complexity of a reads_F, and writes a report to:
            reads_F + ".lib_complexity"

        12/4/15
        """

        ##### If the reads are already sorted, use them, otherwise SORT the reads
        if (reads_F[-7:] == ".sorted"):
            sorted_reads_F = reads_F
        else:
            sorted_reads_F = reads_F + ".sorted"
            sort_cmd = "sort {0} > {1}".format( reads_F, sorted_reads_F )
            os.system( sort_cmd )

        unique_DIR = self.rdir_path('unique')
        RBNS_utils.make_dir( unique_DIR )
        unique_reads_DIR = self.rdir_path('unique/split_reads')
        RBNS_utils.make_dir( unique_reads_DIR )
        mult_reads_DIR = self.rdir_path('unique/split_reads/mult_reads')
        RBNS_utils.make_dir( mult_reads_DIR )
        assert( os.path.exists( mult_reads_DIR ) )

        unique_reads_F = os.path.join( unique_reads_DIR, os.path.basename( reads_F ) )
        unique_reads_f = open( unique_reads_F, "w" )

        num_reads_by_numtimespres_D = {}

        prev_read = ""
        counts_this_read = 1

        total_reads = 0
        #### A dictionary that keeps track of the reads by the number times
        ####    its present (only for >1 occurrence)
        reads_S_by_numtimes_D = {}
        with open( sorted_reads_F ) as f:
            for line in f:
                read = line.strip()
                total_reads += 1
                if (read == prev_read):
                    counts_this_read += 1
                else:
                    try:
                        num_reads_by_numtimespres_D[counts_this_read] += 1
                    except KeyError:
                        num_reads_by_numtimespres_D[counts_this_read] = 1
                    unique_reads_f.write( line )

                    ##### If this read was present multiple times, keep track
                    ####    of it
                    if ( counts_this_read > 1 ):
                        try:
                            reads_S_by_numtimes_D[counts_this_read].add( prev_read )
                        except KeyError:
                            reads_S_by_numtimes_D[counts_this_read] = set( [prev_read] )

                    prev_read = read
                    counts_this_read = 1

        unique_reads_f.close()

        total_num_unique_seqs = sum( num_reads_by_numtimespres_D.values() )
        counts_L = num_reads_by_numtimespres_D.keys()
        counts_L.sort()

        out_log_F = sorted_reads_F.split(".reads")[0] + ".lib_complexity"
        line_by_count_D = {}
        with open( out_log_F, 'w' ) as f:
            f.write( "{0:,} unique {1}mers among {2:,} reads:\n".format(
                total_num_unique_seqs, len( read ), total_reads ) )
            for count in counts_L:
                num_times_line = "{0:,} ({1:.2f}%)".format(
                    num_reads_by_numtimespres_D[count],
                    num_reads_by_numtimespres_D[count] * 100./ total_num_unique_seqs )
                line_by_count_D[count] = num_times_line
                f.write( "{0}x: {1}\n".format( count, num_times_line ) )

        if (reads_F[-7:] != ".sorted") and remove_sorted:
            rm_cmd = "rm {}".format( sorted_reads_F )
            os.system( rm_cmd )

        #if not make_unique_reads_F:
        #    rm_cmd = "rm {}".format( unique_reads_F )
        #    os.system( rm_cmd )
        #    os.system( "rm -rf {}".format( unique_reads_DIR ) )

        #### Go through and make the 'multiplicity' reads files
        num_times_L = num_reads_by_numtimespres_D.keys()
        num_times_L.sort()
        mult_times_L = [x for x in num_times_L if x > 1]
        for num_times in mult_times_L:
            out_basename = "{0}.{1}_times.reads".format(
                    os.path.basename( reads_F ).split(".reads")[0], num_times )
            out_reads_F = os.path.join( mult_reads_DIR, out_basename )
            with open( out_reads_F, "w" ) as f:
                for read in reads_S_by_numtimes_D[num_times]:
                    f.write( read + "\n" )

        return_D = {"line_by_count_D": line_by_count_D}
        if make_unique_reads_F:
            return_D["unique_reads_F"] = unique_reads_F

        return return_D


    def do_counts( self ):
        """
        Runs all of the counts
        """
        counts_types_to_do_L = []
        for count_type in ['naive', 'naive_max_once', 'stream', 'by_position']:
            if (self.settings.get_property(count_type + "_count") == True):
                counts_types_to_do_L.append( count_type )

        self.waiting_jobs = []
        print '\nDoing counts for types...\n'
        pprint.pprint( counts_types_to_do_L )
        print '\n'
        for lib_settings in self.settings.iter_lib_settings():
            for count_type in counts_types_to_do_L:
                for k in self.settings.get_ks(count_type):
                    if self.needs_calculation(lib_settings, count_type, k):
                        print "\t{0}, k={1}".format( count_type, k )
                        if self.counts_on_cluster:
                            self.waiting_jobs.append(
                              RBNS_cluster_utils.launch_counter(
                                lib_settings,
                                count_type,
                                k,
                                self.settings.get_edir()))
                        else:
                            self.run_count(lib_settings, count_type, k)
        if self.counts_on_cluster:
            self.wait_for_jobs_to_complete()


    def make_sure_counts_worked( self ):
        max_reattempts = 2
        for pass_i in range( max_reattempts ):
            if self.verify_counts_ran_successfully():
                return
            else:
                sys.stderr.write('Counts do not seem to all have concluded successfully')
                sys.stderr.write('Will reattempt counts')
                sys.stderr.write('This is retry number: %i' % (pass_i + 1))
                self.do_counts()
        if self.counts_on_cluster:
            self.counts_on_cluster = False
            sys.stderr.write('Counting on the cluster seems to now work well.')
            sys.stderr.write('Switching to local counting')
            self.do_counts()
        raise RuntimeError( 'Counts keep failing :(\nCheck the errors' )



    def verify_counts_ran_successfully( self ):
        for lib_settings in self.settings.iter_lib_settings():
            for count_type in ['naive', 'stream']:
                for k in self.settings.get_ks( count_type ):
                    if self.needs_calculation( lib_settings, count_type, k ):
                        return False
        return True



    def wait_for_jobs_to_complete( self, sleep = 30 ):
        """
         - Waits for the counts jobs to be completed on the qsub.
        """
        while True:
            outputs = [subprocess.Popen('qstat %i' % job_id,
              shell=True, stdout=subprocess.PIPE,
              stderr=subprocess.PIPE).communicate()
              for job_id in self.waiting_jobs]
            completed = map(lambda output: 'Unknown Job' in output[1], outputs)
            if all(completed):
                break
            else:
                jobs_left = sum(map(lambda output:
                  0 if 'Unknown J' in output[1] else 1, outputs))
                print jobs_left, 'jobs left', [
                  job for job, job_complete in zip(self.waiting_jobs, completed) if not job_complete]
            time.sleep(sleep)
        self.waiting_jobs = []


    def needs_calculation(self, lib_settings, count_type, k):
        if self.settings.get_force_recount(count_type):
            return True
        return not lib_settings.counts_exist(count_type, k)



    def initialize_libs( self ):
        """
        - libs: ALL libraries
        - plibs: all protein libraries (non-input libraries)
        - non0_plibs: all libararies w/ protein > 0nM
        """
        self.libs = []
        self.plibs = []
        self.non0_plibs = []
        for lib_settings in self.settings.iter_lib_settings():
            lib = RBNS_lib.RBNS_Lib( self.settings, lib_settings )
            if lib.is_input():
                self.libs = [lib] + self.libs
                self.input_lib = lib
            else:
                self.libs.append( lib )
                self.plibs.append( lib )
                if lib.is_0nM():
                    self.zeronM_lib = lib
                else:
                    self.non0_plibs.append( lib )
        #### If there is no 0nM lib, assign it as None
        try:
            zero_nM_lib = self.zeronM_lib
        except AttributeError:
            self.zeronM_lib = None



    def calculate_all_enrichments( self ):
        """
        sorts all the kmers.
        """
        print 'Calculating enrichments...\n'
        RBNS_utils.make_dir(self.rdir_path('tables'))
        for k, lib in itertools.product(self.settings.get_naiveks(), self.plibs):
            lib.calculate_enrichment( k, self.input_lib )
        for k, lib in itertools.product(self.settings.get_naiveks_max_once(), self.plibs):
            lib.calculate_enrichment_max_once( k, self.input_lib )



    def calculate_all_enrichments_to_0nM(self):
        """
        sorts all the kmers.
        """
        print 'Calculating enrichments to 0 nM...\n'
        RBNS_utils.make_dir(self.rdir_path('tables'))
        try:
            for k, lib in itertools.product(
                    self.settings.get_naiveks(), self.non0_plibs):
                lib.calculate_enrichment_to_0nM( k, self.zeronM_lib )
        #### If there is no 0 nM library
        except AttributeError:
            pass



    def determine_most_enriched_lib( self ):
        """
        - For each k, determines the most enriched library for:
                1. Enrichments relative to Input (self.k2most_enriched_lib)
                2. Enrichments relative to 0 nM (self.self.k2most_enriched_0nM_lib)
        """
        #######################################################################
        ####### < Always use the 5mers as the 'most enriched' library > #######
        most_enriched_lib = self.plibs[0]
        best_enrich = 1.0
        for lib in self.plibs:
            max_enrich = lib.get_max_enrichment( 5 )
            if max_enrich > best_enrich:
                most_enriched_lib = lib
                best_enrich = max_enrich
        if (self.zeronM_lib != None):
            most_enriched_0nM_lib = self.non0_plibs[0]
            best_enrich = 1.0
            for lib in self.non0_plibs:
                max_enrich = lib.get_max_0nM_enrichment( 5 )
                if max_enrich > best_enrich:
                    most_enriched_0nM_lib = lib
                    best_enrich = max_enrich
        ####### </ Always use the 5mers as the 'most enriched' library > ######
        #######################################################################

        self.k2most_enriched_lib = {}
        self.k2most_enriched_0nM_lib = {}
        #### These will have values like "20_nM"
        self.k2most_enriched_lib_annot = {}
        self.k2most_enriched_0nM_lib_annot = {}
        self.k2most_enriched_effectivelib_annot = {} ### to 'input' unless 0 nM is specified
        self.most_enriched_lib_annot_like_20_nM = ""
        for k in self.settings.get_naiveks():
            #### If a conc_for_mostenriched_analyses was passed in the settings
            ####    file, use that library
            conc_for_mostenriched_analyses =\
                self.settings.get_property('conc_for_mostenriched_analyses')

            #### If a conc_for_mostenriched_analyses was passed in, use that
            if (conc_for_mostenriched_analyses != None):
                for lib in self.plibs:
                    if (lib.get_conc() == conc_for_mostenriched_analyses):
                        self.k2most_enriched_lib[k] = lib
                        if (self.zeronM_lib != None):
                            self.k2most_enriched_0nM_lib[k] = lib
                continue

            self.k2most_enriched_lib[k] = most_enriched_lib

            #### If there's a 0 nM library, also get the most enriched library
            ####    when comparing to the 0 nM
            if (self.zeronM_lib == None):
                continue
            self.k2most_enriched_0nM_lib[k] = most_enriched_0nM_lib

        #### Now go through and get the annot's (e.g., " " )
        for k, lib in self.k2most_enriched_lib.iteritems():
            self.k2most_enriched_lib_annot[k] = lib.return_conc_annot_like_20_nM()
            self.k2most_enriched_effectivelib_annot[k] = lib.return_conc_annot_like_20_nM()
        for k, lib in self.k2most_enriched_0nM_lib.iteritems():
            self.k2most_enriched_0nM_lib_annot[k] = lib.return_conc_annot_like_20_nM()
            if ( self.settings.get_property('input_library_for_logos') not in\
                    ["input", "Input"] ):
                self.k2most_enriched_effectivelib_annot[k] = lib.return_conc_annot_like_20_nM()

        #print "\n\nself.k2most_enriched_lib_annot:"
        #pprint.pprint( self.k2most_enriched_lib_annot )
        #print "\n\nself.k2most_enriched_0nM_lib_annot:"
        #pprint.pprint( self.k2most_enriched_0nM_lib_annot )
        #print "\n\nself.k2most_enriched_effectivelib_annot:"
        #pprint.pprint( self.k2most_enriched_effectivelib_annot )
        for ks_L in [5, 6, 7, 4]:
            try:
                self.most_enriched_lib_annot_like_20_nM = self.k2most_enriched_effectivelib_annot[k]
                break
            except KeyError:
                pass


    def sort_all_kmers_by_enrichment( self ):
        """
        - For each k, sorts kmers by decreasing:
            1. Enrichment (to input)
            2. Enrichment (to 0nM)
            3. Binding Fraction

        - Keeps these stored in 3 dictionaries, e.g.:

            self.naively_sorted_kmers = {
                5: [5mer_1, 5mer_2, ...],
                6: [6mer_1, 6mer_2, ...]}
        """
        self.naively_sorted_kmers = {}
        self.naively_sorted_Rto0nM_kmers = {}
        self.naively_max_once_sorted_kmers = {}
        self.naively_max_once_sorted_Rto0nM_kmers = {}
        self.est_bind_frac_sorted_kmers = {}

        #### Sort by enrichments (relative to both input & 0 nM)
        for k in self.settings.get_naiveks():
            self.naively_sorted_kmers[k] =\
              self.sort_kmers_by_enrichment(k, 'naive')
            if (self.zeronM_lib != None):
                self.naively_sorted_Rto0nM_kmers[k] =\
                  self.sort_kmers_by_0nM_enrichment(k, 'naive')

        #### Sort by enrichments, max once per read (relative to both input & 0 nM)
        for k in self.settings.get_naiveks_max_once():
            self.naively_max_once_sorted_kmers[k] =\
              self.sort_kmers_by_enrichment_max_once(k, 'naive')
            if (self.zeronM_lib != None):
                self.self.naively_max_once_sorted_kmers[k] =\
                  self.sort_kmers_by_0nM_enrichment_max_once(k, 'naive')

        #### Sort by estimated binding fractions
        for k in self.settings.get_ks('stream'):
            most_enriched_lib = self.k2most_enriched_lib[k]
            self.est_bind_frac_sorted_kmers[k] =\
              self.sort_lib_by_est_bind_frac(k, most_enriched_lib)


    def sort_kmers_by_enrichment( self,
            k,
            method = 'naive'):
        """
        - Sorts the kmers based on the enrichments of kmers in the most enriched
        library
        - Returns:
                an array of the kmers (as indexes, not strings) in sorted order
        """
        most_enriched_lib = self.k2most_enriched_lib[k]
        if (method == 'naive'):
            enrichments = most_enriched_lib.get_enrichments(k)
        elif (method == 'naive_max_once'):
            enrichments = most_enriched_lib.get_enrichments_max_once(k)
        kmers = range(4 ** k)
        enrichments_kmers = zip(enrichments, kmers)
        enrichments_kmers.sort( reverse = True )
        top_enrich, sorted_kmers = zip(*enrichments_kmers)

        kmers_to_ignore_L = self.settings.get_property( 'kmers_to_ignore' )

        #### If there are no kmers to ignore, ALL can be returned
        if (len( kmers_to_ignore_L ) == 0 ):
            return sorted_kmers

        #### If there are kmers to ignore, screen out all kmers that do contain
        ####    one
        sorted_kmers_L = []
        for kmer_i in sorted_kmers:
            kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
            kmer_passes = True
            for kmer_to_ignore in kmers_to_ignore_L:
                if ( kmer.find( kmer_to_ignore ) != -1 ):
                    kmer_passes = False
            if kmer_passes:
                sorted_kmers_L.append( kmer_i )
        return tuple( sorted_kmers_L )



    def sort_kmers_by_0nM_enrichment( self,
            k,
            method = 'naive'):
        """
        - Sorts the kmers based on the enrichments of kmers in the most enriched
        library
        - Returns:
                an array of the kmers (as indexes, not strings) in sorted order
        """
        most_enriched_lib = self.k2most_enriched_0nM_lib[k]
        if (method == 'naive'):
            enrichments = most_enriched_lib.get_0nM_enrichments(k)
        elif (method == 'naive_max_once'):
            enrichments = most_enriched_lib.get_0nM_enrichments_max_once(k)
        kmers = range(4 ** k)
        enrichments_kmers = zip(enrichments, kmers)
        enrichments_kmers.sort(reverse=True)
        top_enrich, sorted_kmers = zip(*enrichments_kmers)

        kmers_to_ignore_L = self.settings.get_property( 'kmers_to_ignore' )

        #### If there are no kmers to ignore, ALL can be returned
        if (len( kmers_to_ignore_L ) == 0 ):
            return sorted_kmers

        #### If there are kmers to ignore, screen out all kmers that do contain
        ####    one
        sorted_kmers_L = []
        for kmer_i in sorted_kmers:
            kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
            kmer_passes = True
            for kmer_to_ignore in kmers_to_ignore_L:
                if ( kmer.find( kmer_to_ignore ) != -1 ):
                    kmer_passes = False
            if kmer_passes:
                sorted_kmers_L.append( kmer_i )
        return tuple( sorted_kmers_L )




    def sort_lib_by_est_bind_frac(self,
            k,
            lib):
        """
        sorts the kmers based on est. binding fractions in the
        given protein library "lib" for length k.
        returns an array of the kmers (as indexes not strings) in sorted order
        """
        est_bind_fracs = lib.get_stream_libfracs(k)
        kmers = range(4 ** k)
        est_bind_fracs_kmers = zip(est_bind_fracs, kmers)
        est_bind_fracs_kmers.sort(reverse=True)
        top_est_bind_fracs, sorted_kmers = zip(*est_bind_fracs_kmers)
        return sorted_kmers




    def make_enrichment_table( self ):
        """
        Makes a table of the enrichments for the values of k
        Also, writes a pkl with the same information
        """
        kmers_sig_enriched_L_by_k_Zscore_D = {}
        #### A dictionary that contains the "effective" highest enrichments;
        ####    if the input_library_for_logos in "input", these are enrichments
        ####    to the input library; otherwise, they're enrichments to the
        ####    0 nM library (for the most enriched concentration);
        ####    additionally
        effective_enrichments_by_k_D = {}
        self.effective_enrichments_by_k_D = {}
        self.effective_enrichment_libs_by_k_D = {}

        self.enrich_table_F_by_k_D = {}
        self.enrich_table_to_0nM_F_by_k_D = {}

        for k in self.settings.get_property('ks_to_test_naive'):

            kmers_sig_enriched_L_by_k_Zscore_D[k] = {}
            effective_enrichments_by_k_D = {}

            #### Record which libraries were used to calculate the effective
            ####    enrichments
            effective_enrichments_num_conc = ""
            effective_enrichments_denom_conc = "input"

            #### Get the most enriched libs
            most_enriched_lib = self.k2most_enriched_lib[k]
            try:
                most_enriched_lib_of_5mers = self.k2most_enriched_lib[5]
                most_enriched_lib_conc = most_enriched_lib_of_5mers.get_conc_for_fastq()
            except:
                print "ERROR: 5mer were not calculated, so getting the most enriched concentration for {}mers instead".format(
                        k )
                most_enriched_lib_conc = most_enriched_lib.get_conc_for_fastq()

            most_enriched_libs_Rs_L = []
            most_enriched_libs_to_0nM_Rs_L = []

            ############## < ENRICHMENT RELATIVE TO INPUT > ###################
            print '\tWriting Enrichment Table for k=%i' % k
            #### Write the table
            table_f = self.get_rdir_fhandle(
                    'tables/enrichments/{0}_enrichment_R.{1}mers.txt'.format(
                        self.settings.get_property('protein_name'), k))
            table_F = self.rdir_path(
                    'tables/enrichments/{0}_enrichment_R.{1}mers.txt'.format(
                        self.settings.get_property('protein_name'), k))
            self.enrich_table_F_by_k_D[k] = table_F
            self.make_table_header( table_f )
            table_w_adapter_f = self.get_rdir_fhandle(
                    'tables/enrichments/{0}_enrichment_R.{1}mers.mark_adapters.txt'.format(
                        self.settings.get_property('protein_name'), k))
            self.make_table_header( table_w_adapter_f )
            for kmer_i in self.naively_sorted_kmers[k]:
                kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                table_f.write( kmer )
                table_w_adapter_f.write( kmer )
                if RBNS_utils.kmer_in_adapters( kmer,
                        self.settings.get_property('adapter_sequences_l') ):
                    table_w_adapter_f.write( "*" )
                for lib in self.plibs:
                    R = lib.get_enrichment(k, kmer_i)
                    table_f.write('\t{0:.4f}'.format( R ))
                    table_w_adapter_f.write('\t{0:.4f}'.format( R ))
                    if (lib == most_enriched_lib):
                        most_enriched_libs_Rs_L.append( R )
                        effective_enrichments_by_k_D[kmer] = R
                        effective_enrichments_num_conc = lib.get_conc_for_fastq()
                table_f.write('\n')
                table_w_adapter_f.write('\n')
            table_f.close()
            table_w_adapter_f.close()

            #### Get the Z-scores for this enrichment table
            get_Zscores_and_from_R_table( table_F )

            ################# < IF THERE ARE kmers TO IGNORE > ################
            #### If kmers to ignore were passed in, make enrichment tables
            ####    with those kmers displayed at the bottom of the file
            kmers_to_ignore_L = self.settings.get_property( 'kmers_to_ignore' )
            if (kmers_to_ignore_L != []):

                kmers_to_ignore_str = "_".join( kmers_to_ignore_L )
                most_enriched_libs_Rs_L = []

                ############## < ENRICHMENT RELATIVE TO INPUT > ###################
                #### An enrichment dictionary with all of the kmers_to_ignore
                ####    having an enrichment of 1
                modified_enrichment_by_kmers_D = {}
                effective_enrichments_by_k_D = {}
                for lib in self.plibs:
                    modified_enrichment_by_kmers_D[lib.get_conc_for_fastq()] = {}

                end_of_file_lines_L = []
                end_of_file_lines_mark_adapters_L = []
                print '\tWriting Enrichment Table for k={0}, with kmers containing {1} at the bottom'.format(
                        k, kmers_to_ignore_L )

                #### Write the table
                table_f = self.get_rdir_fhandle(
                        'tables/enrichments/{0}_enrichment_R.{1}mers.{2}_containing_at_bottom.txt'.format(
                            self.settings.get_property('protein_name'), k,
                            kmers_to_ignore_str ))
                self.make_table_header( table_f )
                #### A table with a * after kmers that are in the adapters
                table_w_adapter_f = self.get_rdir_fhandle(
                        'tables/enrichments/{0}_enrichment_R.{1}mers.{2}_containing_at_bottom.mark_adapters.txt'.format(
                            self.settings.get_property('protein_name'), k,
                            kmers_to_ignore_str ))
                self.make_table_header( table_w_adapter_f )
                for kmer_i in self.naively_sorted_kmers[k]:
                    kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                    this_line = kmer
                    this_line_mark_adapters = kmer
                    if RBNS_utils.kmer_in_adapters( kmer,
                            self.settings.get_property('adapter_sequences_l') ):
                        this_line_mark_adapters += "*"
                    for lib in self.plibs:
                        this_line += '\t{0:.4f}'.format(
                                lib.get_enrichment(k, kmer_i) )
                        this_line_mark_adapters += '\t{0:.4f}'.format(
                                lib.get_enrichment(k, kmer_i) )
                    this_line += "\n"
                    this_line_mark_adapters += "\n"

                    #### If this kmer doesn't contain any of the
                    ####    kmers_to_ignore_L, write it out immediately; if it
                    ####    does, add it to the list of strings to write at the
                    ####    bottom
                    contains_kmer_to_ignore = False
                    for kmer_to_ignore in kmers_to_ignore_L:
                        if (kmer.find( kmer_to_ignore ) != -1):
                            contains_kmer_to_ignore = True
                    if (contains_kmer_to_ignore == False):
                        table_f.write( this_line )
                        table_w_adapter_f.write( this_line_mark_adapters )
                        for lib in self.plibs:
                            R =  lib.get_enrichment(k, kmer_i)
                            modified_enrichment_by_kmers_D[lib.get_conc_for_fastq()][kmer] = R
                            if (lib == most_enriched_lib):
                                most_enriched_libs_Rs_L.append( R )
                                effective_enrichments_by_k_D[kmer] = R
                                effective_enrichments_num_conc = lib.get_conc_for_fastq()

                    else:
                        end_of_file_lines_L.append( this_line )
                        end_of_file_lines_mark_adapters_L.append( this_line_mark_adapters )
                        for lib in self.plibs:
                            modified_enrichment_by_kmers_D[lib.get_conc_for_fastq()][kmer] =\
                                1.0
                            effective_enrichments_by_k_D[kmer] = 1.

                #### Now write out the end_of_file_lines_L
                table_f.write( "\n\nkmers containing {}:\n".format(
                    kmers_to_ignore_L ) )
                table_f.write( "".join( end_of_file_lines_L ) )

                table_f.close()

                table_w_adapter_f.write( "\n\nkmers containing {}:\n".format(
                    kmers_to_ignore_L ) )
                table_w_adapter_f.write( "".join(
                    end_of_file_lines_mark_adapters_L ) )

                table_w_adapter_f.close()

                #### Pickle all of the enrichment dictionaries, with the
                ####    kmers to ignore having enrichment of 1.
                for lib in self.plibs:
                    enrich_D_pkl_F = lib.return_enrich_D_pkl_to_input( k )
                    beginning_D_F, ending_D_F = enrich_D_pkl_F.split( "input" )
                    out_D_F = beginning_D_F + "input.ignore_{}".format( kmers_to_ignore_str ) +\
                            ending_D_F
                    with open( out_D_F, "wb" ) as f:
                        cPickle.dump( modified_enrichment_by_kmers_D[lib.get_conc_for_fastq()], f )
            ################ </ IF THERE ARE kmers TO IGNORE > ################


            ############### < THE SIGNIFICANTLY ENRICHED kmers > ##############
            #### Get the mean & std R's for the most enriched_lib
            mean_R, std_R = RBNS_utils.mean_std( most_enriched_libs_Rs_L )
            #### Make a table of the significantly enriched kmers
            for Z_score in [1., 2., 3.]:
                try:
                    R_thresh = mean_R + (Z_score * std_R)
                except TypeError:
                    R_thresh = 100.
                kmers_sig_enriched_L_by_k_Zscore_D[k][Z_score] = []
                #### Write the table
                table_f = self.get_rdir_fhandle(
                        'tables/enrichments/{0}_enrichment_R.{1}mers.sig_R_Zscore{2:.1f}_in_{3}.txt'.format(
                            self.settings.get_property('protein_name'), k,
                            Z_score, most_enriched_lib_conc ))
                self.make_table_header( table_f )
                for kmer_i in self.naively_sorted_kmers[k]:
                    kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                    R_in_most_enriched_lib = most_enriched_lib.get_enrichment(k, kmer_i)
                    if (R_in_most_enriched_lib < R_thresh):
                        break
                    if RBNS_utils.kmer_to_ignore_in_kmer( kmer, kmers_to_ignore_L ):
                        continue
                    table_f.write(kmer)
                    for lib in self.plibs:
                        R = lib.get_enrichment(k, kmer_i)
                        table_f.write('\t{0:.4f}'.format( R ))
                    table_f.write('\n')

                    #### If this kmer does not contain a kmer to ignore, add
                    ####    it to kmers_sig_enriched_L_by_k_Zscore_D
                    if (RBNS_utils.kmer_to_ignore_in_kmer( kmer, kmers_to_ignore_L ) == False):
                        kmers_sig_enriched_L_by_k_Zscore_D[k][Z_score].append( kmer )

                table_f.close()

            self.effective_enrichments_by_k_D[k] = effective_enrichments_by_k_D
            self.effective_enrichment_libs_by_k_D[k] =\
                    {"num": effective_enrichments_num_conc,
                     "denom": effective_enrichments_denom_conc }

            ############## </ ENRICHMENT RELATIVE TO INPUT > ##################



            ############## < ENRICHMENT RELATIVE TO 0 nM > ####################
            if (self.zeronM_lib == None):
                continue

            most_enriched_to_0nM_lib = self.k2most_enriched_0nM_lib[k]
            most_enriched_to_0nM_conc = most_enriched_to_0nM_lib.get_conc_for_fastq()

            #### If the 0 nM library should be used for enrichments, get
            ####    most_enriched_libs_Rs_L = []
            if ( self.settings.get_property( "input_library_for_logos" ) != "input"):
                get_Rs = True
                effective_enrichments_by_k_D = {}
                effective_enrichments_denom_conc = "0"
            else:
                get_Rs = False

            print '\tWriting 0 nM Enrichment Table for k=%i' % k
            #write table
            table_f = self.get_rdir_fhandle(
                    'tables/enrichments/{0}_enrichment_R_to_0nM.{1}mers.txt'.format(
                        self.settings.get_property('protein_name'), k))
            table_F = self.rdir_path(
                    'tables/enrichments/{0}_enrichment_R_to_0nM.{1}mers.txt'.format(
                        self.settings.get_property('protein_name'), k))
            self.enrich_table_to_0nM_F_by_k_D[k] = table_F
            self.make_0nM_table_header(table_f)
            for kmer_i in self.naively_sorted_Rto0nM_kmers[k]:
                kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                table_f.write(kmer)
                for lib in self.non0_plibs:
                    R = lib.get_0nM_enrichment(k, kmer_i)
                    table_f.write('\t{0:.4f}'.format( R ))
                    if (lib == most_enriched_to_0nM_lib):
                        if (RBNS_utils.kmer_to_ignore_in_kmer( kmer, kmers_to_ignore_L ) == False):
                            most_enriched_libs_to_0nM_Rs_L.append( R )
                        if (get_Rs == True):
                            effective_enrichments_by_k_D[kmer] = R
                            effective_enrichments_num_conc = lib.get_conc_for_fastq()
                table_f.write('\n')
            table_f.close()
            #### Get the Z-scores for this enrichment table
            get_Zscores_and_from_R_table( table_F )

            ############### < THE SIGNIFICANTLY ENRICHED kmers > ##############
            #### Get the mean & std R's for the most enriched_lib
            mean_R, std_R = RBNS_utils.mean_std( most_enriched_libs_to_0nM_Rs_L )
            #### Make a table of the significantly enriched kmers
            for Z_score in [1., 2., 3.]:
                R_thresh = mean_R + (Z_score * std_R)
                if (get_Rs == True):
                    kmers_sig_enriched_L_by_k_Zscore_D[k][Z_score] = []
                #### Write the table
                table_f = self.get_rdir_fhandle(
                        'tables/enrichments/{0}_enrichment_R_to_0nM.{1}mers.sig_R_Zscore{2:.1f}_in_{3}.txt'.format(
                            self.settings.get_property('protein_name'), k,
                            Z_score, most_enriched_lib_conc ))
                self.make_0nM_table_header(table_f)
                for kmer_i in self.naively_sorted_Rto0nM_kmers[k]:
                    kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                    R_in_most_enriched_lib = most_enriched_to_0nM_lib.get_enrichment(k, kmer_i)
                    if (R_in_most_enriched_lib < R_thresh):
                        break
                    if (self.settings.get_property( 'kmers_to_ignore' ) != []) and\
                            (RBNS_utils.kmer_to_ignore_in_kmer( kmer, kmers_to_ignore_L )):
                        continue
                    table_f.write( kmer )
                    for lib in self.non0_plibs:
                        R = lib.get_enrichment(k, kmer_i)
                        table_f.write('\t{0:.4f}'.format( R ))
                        if (get_Rs == True) and (lib == most_enriched_lib):
                            kmers_sig_enriched_L_by_k_Zscore_D[k][Z_score].append( kmer )
                    table_f.write('\n')
                table_f.close()
            ############## </ ENRICHMENT RELATIVE TO 0 nM > ###################

            ############### < IF THERE ARE kmers TO IGNORE > ##################
            #### If kmers to ignore were passed in, make enrichment tables
            ####    with those kmers displayed at the bottom of the file
            if (self.settings.get_property( 'kmers_to_ignore' ) != []):

                #### An enrichment dictionary with all of the kmers_to_ignore
                ####    having an enrichment of 1
                modified_enrichment_by_kmers_D = {}
                for lib in self.non0_plibs:
                    modified_enrichment_by_kmers_D[lib.get_conc_for_fastq()] = {}

                end_of_file_lines_L = []
                print '\tWriting 0nM Enrichment Table for k={0}, with kmers containing {1} at the bottom'.format(
                        k, kmers_to_ignore_L )
                #write table
                table_f = self.get_rdir_fhandle(
                        'tables/enrichments/{0}_enrichment_R_to_0nM.{1}mers.{2}_containing_at_bottom.txt'.format(
                            self.settings.get_property('protein_name'), k,
                            kmers_to_ignore_str ))
                self.make_0nM_table_header( table_f )
                for kmer_i in self.naively_sorted_Rto0nM_kmers[k]:
                    kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                    this_line = kmer
                    for lib in self.non0_plibs:
                        this_line += '\t{0:.4f}'.format(
                                lib.get_0nM_enrichment(k, kmer_i) )
                    this_line += "\n"

                    #### If this kmer doesn't contain any of the
                    ####    kmers_to_ignore_L, write it out immediately; if it
                    ####    does, add it to the list of strings to write at the
                    ####    bottom
                    contains_kmer_to_ignore = False
                    for kmer_to_ignore in kmers_to_ignore_L:
                        if (kmer.find( kmer_to_ignore ) != -1):
                            contains_kmer_to_ignore = True
                    if (contains_kmer_to_ignore == False):
                        table_f.write( this_line )
                        for lib in self.non0_plibs:
                            R = lib.get_0nM_enrichment(k, kmer_i)
                            modified_enrichment_by_kmers_D[lib.get_conc_for_fastq()][kmer] =\
                                    R
                            if (get_Rs == True) and (lib == most_enriched_to_0nM_lib):
                                effective_enrichments_by_k_D[kmer] = R
                                effective_enrichments_num_conc = lib.get_conc()


                    else:
                        end_of_file_lines_L.append( this_line )
                        for lib in self.non0_plibs:
                            modified_enrichment_by_kmers_D[lib.get_conc_for_fastq()][kmer] =\
                                    1.0
                            if (get_Rs == True) and (lib == most_enriched_to_0nM_lib):
                                effective_enrichments_by_k_D[kmer] = 1.

                if (get_Rs == True):
                    self.effective_enrichments_by_k_D[k] = effective_enrichments_by_k_D
                    self.effective_enrichment_libs_by_k_D[k] =\
                            {"num": effective_enrichments_num_conc,
                             "denom": effective_enrichments_denom_conc }

                #### Now write out the end_of_file_lines_L
                table_f.write( "\n\nkmers containing {}:\n".format(
                    kmers_to_ignore_L ) )
                table_f.write( "".join( end_of_file_lines_L ) )

                table_f.close()

                #### Pickle all of the enrichment to 0nM dictionaries, with the
                ####    kmers to ignore having enrichment of 1.
                for lib in self.non0_plibs:
                    enrich_D_pkl_F = lib.return_enrich_D_pkl_to_0nM( k )
                    beginning_D_F, ending_D_F = enrich_D_pkl_F.split( "0nM" )
                    out_D_F = beginning_D_F + "0nM.ignore_{}".format( kmers_to_ignore_str ) +\
                            ending_D_F
                    with open( out_D_F, "wb" ) as f:
                        cPickle.dump( modified_enrichment_by_kmers_D[lib.get_conc_for_fastq()], f )
            ############### </ IF THERE ARE kmers TO IGNORE > #################
            self.effective_enrichments_by_k_D[k] = effective_enrichments_by_k_D
            self.effective_enrichment_libs_by_k_D[k] =\
                    {"num": effective_enrichments_num_conc,
                     "denom": effective_enrichments_denom_conc }

        print '\nTables successfully made; outputs in: {}\n'.format(
                os.path.join( self.settings.get_rdir(), "tables" ) )
        self.kmers_sig_enriched_L_by_k_Zscore_D = kmers_sig_enriched_L_by_k_Zscore_D

        #### Go through and pickle the effective enrichments
        enrichment_Ds_DIR = self.rdir_path('enrichment_Ds')
        if not os.path.exists( enrichment_Ds_DIR ):
            os.makedirs( enrichment_Ds_DIR )
        for k, enrichments_D in self.effective_enrichments_by_k_D.iteritems():
            out_D_F = os.path.join( enrichment_Ds_DIR,
                    "effective_enrichments_D.{}.pkl".format( k ) )
            RBNS_utils.pkl_vals_by_kmer_D_w_formatfile( enrichments_D, out_D_F )

            #### A .txt file to record which libraries were used to
            ####    calculate the effective enrichments
            log_txt_F = os.path.join( enrichment_Ds_DIR,
                    "effective_enrichments_D.{}.libs.txt".format( k ) )
            with open( log_txt_F, "w" ) as f:
                f.write( "Pulldown_lib: {0}\nInput_lib: {1}".format(
                    int(self.effective_enrichment_libs_by_k_D[k]["num"]),
                    self.effective_enrichment_libs_by_k_D[k]["denom"] ) )


    def get_nt_freqs_by_position( self ):
        """
        - Gets the counts (aka, k = 1mers) of the nt frequencies by position
            within the read
        """
        self.waiting_jobs = []
        print '\nGetting nt frequencies at each read position...\n'
        for lib_settings in self.settings.iter_lib_settings():
            for k in [1]:
                if self.needs_calculation(lib_settings, 'by_position', k):
                    if self.counts_on_cluster:
                        self.waiting_jobs.append(
                          RBNS_cluster_utils.launch_counter(
                            lib_settings,
                            'by_position',
                            k,
                            self.settings.get_edir()))
                    elif not self.counts_on_cluster:
                        self.run_count(lib_settings, 'by_position', k)
        if self.counts_on_cluster:
            self.wait_for_jobs_to_complete()


    def make_tables(self):
        RBNS_utils.make_dir( self.rdir_path('analyses') )
        self.make_enrichment_table()
        if ( self.quick == "get_enrichments" ):
            return
        if self.settings.get_ks('stream'):
            self.make_SKA_table()
        self.make_counts_and_freqs_tables()
        self.make_adapter_seq_tables()
        self.make_Btable()
        #### Make tables & plots by position
        if self.settings.get_ks('by_position'):
            self.make_tables_each_kmer_by_position()


    def make_table_header(self,
            of,
            include_input = False):
        """
        - Writes a header to tables (protein + concentrations)
        - If include_input == True, adds "Input" as the last column
        """
        of.write('[%s]' % self.settings.get_property('protein_name_for_plotting'))
        for lib in self.libs:
            if (include_input == False):
                if (lib.is_input() == False):
                    of.write('\t{0}'.format( lib.get_conc_for_title() ))
            else:
                if (lib.is_input() == False):
                    of.write('\t{0}'.format( lib.get_conc_for_title() ))
                else:
                    of.write( '\tInput' )
        of.write( '\n' )


    def make_0nM_table_header(self,
            of):
        """
        - Writes a header to tables (Only including protein > 0nM concs)
        """
        of.write('[%s]' % self.settings.get_property('protein_name_for_plotting'))
        for lib in self.libs:
            if (lib.is_input() == False) and (lib.is_0nM() == False):
                of.write('\t{0}'.format( lib.get_conc_for_title() ))
        of.write( '\n' )


    def make_counts_and_freqs_tables(self):
        """
        For each k, makes 4 tables (one library per column of each table):
                1. kmer counts (alphabetical order)
                2. kmer frequencies (alphabetical order)
                3. kmer counts (by decreasing R)
                4. kmer frequencies (by decreasing R)
        """
        print '\n\n' + '='*18 + ' < Making counts & frequencies tables > ' +\
                '='*17 + '\n'
        for k in self.settings.get_property('ks_to_test_naive'):
            print '\tfor k=%i' % k

            of = self.get_rdir_fhandle('tables/counts_and_freqs',
                    '{}mer_counts.txt'.format(k))
            self.make_table_header(of, include_input = True)
            for kmeri in range(4 ** k):
                kmer_str = RBNS_utils.get_kmer_from_index(k, kmeri)
                of.write('\n' + kmer_str)
                for lib in self.libs:
                    of.write('\t%i' %
                     lib.get_naive_count_by_index(k, kmeri))
            of.close()

            #### frequencies
            of = self.get_rdir_fhandle('tables/counts_and_freqs',
                    '{}mer_freqs.txt'.format(k))
            self.make_table_header(of, include_input = True)
            total_counts_by_lib_L = []
            for lib in self.libs:
                total_counts = 0.
                for kmeri in range(4 ** k):
                    total_counts += lib.get_naive_count_by_index(k, kmeri)
                total_counts_by_lib_L.append( total_counts )

            ##### Dictionaries of the frequencies by kmer in each of the libs
            freqs_by_kmer_Ds_L = []
            for lib_num, lib in enumerate( self.libs ):
                freqs_by_kmer_Ds_L.append( {} )
            for kmeri in range(4 ** k):
                kmer_str = RBNS_utils.get_kmer_from_index(k, kmeri)
                of.write('\n' + kmer_str)
                for lib_num, lib in enumerate( self.libs ):
                    freq = lib.get_naive_count_by_index(k, kmeri) /\
                            total_counts_by_lib_L[lib_num]
                    #### Add this kmer's freq to its freqs_by_kmer_D
                    freqs_by_kmer_Ds_L[lib_num][kmer_str] = freq
                    of.write('\t{0:.3g}'.format( freq ))
            of.close()

            #### Pickle all of the freqs_by_kmer_Ds in a "frequency_Ds" sub_DIR
            freqs_Ds_DIR = os.path.join( self.settings.get_rdir(), "frequency_Ds" )
            RBNS_utils.make_dir( freqs_Ds_DIR )
            for lib_num, lib in enumerate( self.libs ):
                freqs_D_basename = "{0}_{1}.{2}mer.frequencies.pkl".format(
                    self.settings.get_property('protein_name'),
                        lib.get_conc_for_fastq(), k)
                freqs_D_F = os.path.join( freqs_Ds_DIR, freqs_D_basename )
                cPickle.dump( freqs_by_kmer_Ds_L[lib_num],
                        open( freqs_D_F, 'wb' ))


            #### kmer counts sorted by descending enrichment
            of_sorted = self.get_rdir_fhandle(
              'tables/counts_and_freqs/{}mer_counts.sorted_by_R.txt'.format( k ))
            self.make_table_header(of_sorted, include_input = True)
            for kmeri in self.naively_sorted_kmers[k]:
                kmer_str = RBNS_utils.get_kmer_from_index(k, kmeri)
                of_sorted.write('\n' + kmer_str)
                for lib in self.libs:
                    of_sorted.write('\t%i' %
                      lib.get_naive_count_by_index(k, kmeri))
            of_sorted.close()

            #### kmer freqs sorted by descending enrichment
            of_sorted = self.get_rdir_fhandle(
              'tables/counts_and_freqs/{}mer_freqs.sorted_by_R.txt'.format( k ))
            self.make_table_header(of_sorted, include_input = True)
            for kmeri in self.naively_sorted_kmers[k]:
                kmer_str = RBNS_utils.get_kmer_from_index(k, kmeri)
                of_sorted.write('\n' + kmer_str)
                for lib_num, lib in enumerate( self.libs ):
                    freq = lib.get_naive_count_by_index(k, kmeri) /\
                            total_counts_by_lib_L[lib_num]
                    of_sorted.write( '\t{0:.3g}'.format( freq ))
            of_sorted.close()
        print '\n' + '='*17 + ' </ Making counts & frequencies tables > ' +\
                '='*17 + "\n\n"



    def make_adapter_seq_tables( self ):
        """
        - Makes a table of the adapter sequence frequencies & enrichments in
            each library
        """
        ks_L = self.settings.get_ks( 'naive' )
        adapters_L = self.settings.get_property('adapter_sequences_l')
        #### Make a table with each adapter sequence enrichment & frequencies
        ####    ( First, get the frequencies_D for the library that's the
        ####        effective input library)
        for k in ks_L:
            #### Make a table with the frequencies of each adapter sequence
            ####    in ALL of the libraries

            for lib in self.libs:
                if (lib.is_denom_for_enrichments() == True):
                    effective_input_freqs_D = lib.return_frequencies_D( k )
                    break
            for lib in self.libs:
                out_basename = os.path.join( "{0}.{1}mers.{2}.Adapters.EnrichmentAndFreqs.txt".format(
                    self.settings.get_property('protein_name'),
                    k,
                    lib.get_conc_for_fastq() ) )
                adapter_tables_DIR = os.path.join( self.settings.get_rdir(),
                        "tables/adapters" )
                RBNS_utils.make_dir( adapter_tables_DIR )
                out_txt_F = os.path.join( adapter_tables_DIR, out_basename )

                #### Load the frequencies dictionary
                freqs_D = lib.return_frequencies_D( k )

                ##### If this is NOT the library for the denominator of the main
                #####    enrichments, load the enrichments
                #if (lib.is_denom_for_enrichments() == False):
                #    enrichment_D = self.return_main_enrichments_D( k )

                out_f = open( out_txt_F, 'w' )

                #### Make a header line
                out_f.write( "\tFreq.\tR to {}".format(
                    self.settings.get_property( "input_library_for_logos" ) ) )

                #### Go through each of the adapter sequences
                for adapter_idx, adapter_seq in enumerate( adapters_L ):
                    out_f.write( "\n\n" )
                    for start_pos in range( len( adapter_seq ) - k + 1 ):
                        adapter_kmer = adapter_seq[start_pos:(start_pos + k)]
                        adapter_freq_this_lib = freqs_D[adapter_kmer]
                        adapter_freq_effective_input_lib =\
                                effective_input_freqs_D[adapter_kmer]
                        R = adapter_freq_this_lib / adapter_freq_effective_input_lib
                        out_f.write( "{0}\t{1:.3g}\t{2:.3g}\t{3:.3f}\n".format(
                            adapter_kmer,
                            adapter_freq_this_lib,
                            adapter_freq_effective_input_lib,
                            R ) )

                out_f.close()

        for k in ks_L:
            #### Make a table with the frequencies of each adapter sequence
            ####    in ALL of the libraries
            out_basename = os.path.join( "{0}.{1}mers.Adapters.freqs_all_libs.txt".format(
                self.settings.get_property('protein_name'),
                k ) )
            out_txt_F = os.path.join( adapter_tables_DIR, out_basename )
            out_f = open( out_txt_F, 'w' )

            freqs_Ds_L = []
            for lib in self.libs:
                out_f.write( "\t{}".format( lib.get_conc_for_title() ) )
                #### Load the frequencies dictionary
                freqs_D = lib.return_frequencies_D( k )
                freqs_Ds_L.append( freqs_D )

            #### Go through each of the adapter sequences
            for adapter_idx, adapter_seq in enumerate( adapters_L ):
                out_f.write( "\n" )
                for start_pos in range( len( adapter_seq ) - k + 1 ):
                    adapter_kmer = adapter_seq[start_pos:(start_pos + k)]
                    out_f.write( "\n" + adapter_kmer )
                    #### Go through each library
                    for freqs_D in freqs_Ds_L:
                        adapter_freq = freqs_D[adapter_kmer]
                        out_f.write( "\t{0:.3g}".format( adapter_freq ) )

            out_f.close()


    def make_Btable( self ):
        """
        - Makes a table of the B values (see Eq. 18 of the
            Supp. Material of Lambert et al. Mol Cell 2014)
        """
        for k in self.settings.get_property('ks_to_test_naive'):
            t_of = self.get_rdir_fhandle('tables/B_factors',
              'B_table.%i.txt' % k)
            self.make_table_header(t_of)
            for kmeri, kmer in enumerate(RBNS_utils.yield_kmers(k)):
                t_of.write(kmer + '\t')
                t_of.write('\t'.join(
                  [str(lib.calcB(kmer)) for lib in self.plibs]) + '\n')
            t_of.close()



    def make_tables_each_kmer_by_position( self ):
        """
        - Makes tables of the kmers by position within read
        """

        out_DIR = os.path.join( self.settings.get_rdir(), "tables/by_position" )
        ks_L = self.settings.get_ks( 'by_position' )

        for k in ks_L:
            out_k_DIR = os.path.join( out_DIR, str(k) )
            os.system( "mkdir -p {}".format( out_k_DIR ) )

            freq_D_DIR = os.path.join( self.settings.get_rdir(),
                    "frequency_Ds" )

            str_concs_L = []
            int_concs_L = []
            freqs_Ds_by_conc_D = {}
            num_start_pos = 0
            #### Go through each of the libraries
            for lib in self.libs:

                #### Load the frequencies by position
                freq_D_basename = "{0}_{1}.{2}mer.frequencies.by_position.pkl".format(
                                self.settings.get_property( "protein_name" ),
                                lib.get_conc_for_fastq(),
                                k )
                freq_D_F = os.path.join( freq_D_DIR, freq_D_basename )
                freqs_by_pos_D = cPickle.load( open( freq_D_F ) )
                num_start_pos = len( freqs_by_pos_D )

                try:
                    conc_name = int( lib.get_conc_for_fastq() )
                    int_concs_L.append( conc_name )
                except ValueError:
                    conc_name = lib.get_conc_for_fastq()
                    str_concs_L.append( conc_name )

                freqs_Ds_by_conc_D[conc_name] = freqs_by_pos_D

            #### Sort the conc_names so they go in the order of:
            ####    ['Input', 0, 5, 20, 120, 320, 1300]
            int_concs_L.sort()
            all_concs_L = str_concs_L + int_concs_L

            #### Now go through each kmer and make an out table for it
            for kmer in RBNS_utils.yield_kmers( k ):
                out_txt_F = os.path.join( out_k_DIR,
                    "{0}_{1}.by_position.txt".format(
                        self.settings.get_property( "protein_name" ), kmer ) )
                out_txt_f = open( out_txt_F, "w" )
                out_txt_f.write( "\t" )
                for i in range( num_start_pos ):
                    out_txt_f.write( "{}\t".format( i ) )
                out_txt_f.write( "\n" )
                #### Go through each library
                for conc_name in all_concs_L:
                    freqs_by_pos_kmer_D = freqs_Ds_by_conc_D[conc_name]
                    freqs_by_pos_L = []
                    for pos in range( num_start_pos ):
                        freqs_by_kmer_thispos_D = freqs_by_pos_kmer_D[pos]
                        freqs_by_pos_L.append( freqs_by_kmer_thispos_D[kmer] )
                    vals_by_pos_L = [x * len( freqs_by_pos_kmer_D )/sum( freqs_by_pos_L )\
                            for x in freqs_by_pos_L]
                    vals_by_pos_str = ["{0:.3f}".format( x ) for x in vals_by_pos_L]
                    out_txt_f.write( str(conc_name) + "\t" + "\t".join( vals_by_pos_str ) + "\n" )

                out_txt_f.close()




    def make_SKA_table( self ):
        """"
        - Makes tables of the streaming kmer (SKA) library fractions
        """

        #### Go through all of the k's
        for k in self.settings.get_ks('stream'):
            print '\tWriting SKA libfrac Table for k=%i' % k

            ##### A table with the kmers ordered by descending enrichment
            table_f = self.get_rdir_fhandle( 'tables/lib_frac',
                    '{0}_est_binding_frac.{1}mers.ordered_by_enrichment.txt'.format(
                        self.settings.get_property('protein_name'), k))
            self.make_table_header(table_f)
            for kmer_i in self.naively_sorted_kmers[k]:
                assert isinstance(kmer_i, int)
                kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                table_f.write(kmer)
                for lib in self.plibs:
                    table_f.write('\t%g' % lib.get_stream_libfrac(k, kmer_i))
                table_f.write('\n')
            table_f.close()

            ##### A table with the kmers ordered by descending
            #####   estimated binding fraction
            table_f = self.get_rdir_fhandle('tables/lib_frac',
                    '{0}_est_binding_frac.{1}mers.txt'.format(
                        self.settings.get_property('protein_name'), k))
            self.make_table_header(table_f)
            for kmer_i in self.est_bind_frac_sorted_kmers[k]:
                assert isinstance(kmer_i, int)
                kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                table_f.write(kmer)
                for lib in self.plibs:
                    table_f.write('\t%g' % lib.get_stream_libfrac(k, kmer_i))
                table_f.write('\n')
            table_f.close()

            ############### < IF THERE ARE kmers TO IGNORE > ##################
            #### If kmers to ignore were passed in, make est. binding fraction
            ####    tables with those kmers displayed at the bottom of the file
            if (self.settings.get_property( 'kmers_to_ignore' ) != []):

                kmers_to_ignore_L = self.settings.get_property( 'kmers_to_ignore' )
                kmers_to_ignore_str = "_".join( kmers_to_ignore_L )

                end_of_file_lines_L = []
                print '\tWriting est binding fraction for k={0}, with kmers containing {1} at the bottom'.format(
                        k, kmers_to_ignore_L )
                table_f = self.get_rdir_fhandle( 'tables/lib_frac',
                        '{0}_est_binding_frac.{1}mers.ordered_by_enrichment.{2}_containing_at_bottom.txt'.format(
                            self.settings.get_property('protein_name'), k,
                            kmers_to_ignore_str ))
                self.make_table_header( table_f )
                for kmer_i in self.naively_sorted_kmers[k]:
                    assert isinstance(kmer_i, int)
                    kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)

                    this_line = kmer
                    for lib in self.plibs:
                        this_line += '\t{0:.4g}'.format(
                                lib.get_stream_libfrac(k, kmer_i) )
                    this_line += "\n"
                    #### If this kmer doesn't contain any of the
                    ####    kmers_to_ignore_L, write it out immediately; if it
                    ####    does, add it to the list of strings to write at the
                    ####    bottom
                    contains_kmer_to_ignore = False
                    for kmer_to_ignore in kmers_to_ignore_L:
                        if (kmer.find( kmer_to_ignore ) != -1):
                            contains_kmer_to_ignore = True
                    if (contains_kmer_to_ignore == False):
                            table_f.write( this_line )
                    else:
                        end_of_file_lines_L.append( this_line )

                #### Now write out the end_of_file_lines_L
                table_f.write( "\n\nkmers containing {}:\n".format(
                    kmers_to_ignore_L ) )
                table_f.write( "".join( end_of_file_lines_L ) )

                table_f.close()
            ############### </ IF THERE ARE kmers TO IGNORE > #################

            ##### A table with est. binding fractions w/ the kmers ordered by
            #####   descending enrichment to 0 nM (if there is a 0 nM library)
            if (self.zeronM_lib == None):
                continue
            table_f = self.get_rdir_fhandle('tables/lib_frac',
                    '{0}_est_binding_frac.{1}mers.ordered_by_enrichment_to_0nM.txt'.format(
                        self.settings.get_property('protein_name'), k))
            self.make_table_header(table_f)
            for kmer_i in self.naively_sorted_Rto0nM_kmers[k]:
                assert isinstance(kmer_i, int)
                kmer = RBNS_utils.get_kmer_from_index(k, kmer_i)
                table_f.write(kmer)
                for lib in self.plibs:
                    table_f.write('\t%g' % lib.get_stream_libfrac(k, kmer_i))
                table_f.write('\n')
            table_f.close()



    ###########################################################################
    ################################# < COUNTS > ##############################

    def run_count( self,
            lib_settings,
            count_type,
            k ):
        """
        - Runs a particular count (of count_type) for kmers for the library
            with lib_settings
        """
        split_reads = lib_settings.get_split_reads()
        out_pkl = lib_settings.counts_file(count_type, k)
        RBNS_utils.make_dir(os.path.dirname(out_pkl))
        print count_type
        if count_type == 'naive':
            count_naive(split_reads, k, out_pkl)
        elif count_type == 'naive_max_once':
            count_naive_max_once(split_reads, k, out_pkl)
        elif count_type == 'stream':
            count_stream(split_reads, k, out_pkl)
        elif count_type == 'by_position':
            count_by_position(split_reads, k, out_pkl)
        else:
            raise ValueError('Unknown count type: %s ' % count_type)

    ################################# </ COUNTS > #############################
    ###########################################################################


    def return_reads_F_annot_tuples_L( self,
            reads_type = "original",
            sort_by_increasing_RBP_conc = False ):
        """
        - Returns a dictionary of [(reads_F, annot), ...], with a tuple
            for each library
            e.g., [(reads_F, "0 nM"), ..., (reads_F, "Input")]
            - or if the input_library_for_logos is 0:
                [('/net/uorf/data/backup/RBNS_results/EWSR1/split_reads/EWSR1_0.reads',
                  'Input'),
                  ...
                 ('/net/uorf/data/backup/RBNS_results/EWSR1/split_reads/EWSR1_1300.reads',
                     '1300 nM')]
        """
        reads_Fs_annot_tuples_L = []
        for lib_settings in self.settings.iter_lib_settings():
            #### Either 'Input' or "5 nM"
            annot = lib_settings.return_annot()
            if ( reads_type == "original" ) or\
                    ((type(reads_type) is dict) and ( reads_type["descrip"] == "num_kmer_occurrences" )):
                if ( reads_type == "original" ):
                    reads_F = lib_settings.get_split_reads()
                elif ( reads_type["descrip"] == "num_kmer_occurrences" ):
                    reads_F = lib_settings.return_split_reads_F_w_num_kmer_occurrences(
                            reads_type["k"],
                            reads_type["descrip_string"],
                            reads_type["num_kmer_occurrences"] )
                #### If the 'input' library to use should be the 0 nM, do not
                ####    include the input library AND use annot = "input" for the
                ####    0 nM library
                if (self.settings.get_property( "input_library_for_logos" ) == "input"):
                    reads_Fs_annot_tuples_L.append( ( reads_F, annot ) )
                else:
                    if (annot == "Input" ):
                        pass
                    elif (annot == "0 nM" ):
                        reads_Fs_annot_tuples_L.append( ( reads_F, "Input" ) )
                    else:
                        reads_Fs_annot_tuples_L.append( ( reads_F, annot ) )
            elif ( reads_type == "by_num_CG" ):
                split_reads_Fs_by_numCG_D = lib_settings.get_split_reads_by_numCG_D()
                for num_CG, reads_F in split_reads_Fs_by_numCG_D.iteritems():
                    annot_with_CG = annot + ".{}CG".format( num_CG )
                    reads_Fs_annot_tuples_L.append( ( reads_F, annot_with_CG ) )

        #### If the list should be retured in the order:
        ####    [ Input, 0, 5, 20, ... ]
        if sort_by_increasing_RBP_conc:
            readsF_annot_RBPconc_T_L = []
            for tupl in reads_Fs_annot_tuples_L:
                try:
                    readsF_annot_RBPconc_T_L.append(
                            ( tupl[0],
                                tupl[1],
                                float( tupl[1].split( ' ' )[0] ) ) )
                #### If it's the 'input' library
                except ValueError:
                    readsF_annot_RBPconc_T_L.append(
                            ( tupl[0],
                                tupl[1],
                                -1. ) )
            readsF_annot_RBPconc_T_L.sort( key = lambda x: x[2] )
            reads_Fs_annot_tuples_L = [ (tupl[0], tupl[1]) for tupl in\
                    readsF_annot_RBPconc_T_L ]

        return reads_Fs_annot_tuples_L




    def return_reads_F_annot_tuples_L_with_input_first( self ):
        """
        - Returns a dictionary of [(reads_F, annot), ...], with a tuple
            for each library
            e.g., [(reads_F, "Input"), (reads_F, "0 nM"), ...]
        """
        reads_Fs_annot_tuples_L = self.return_reads_F_annot_tuples_L()

        valtosorton_tuple_T_L = []
        for tupl in reads_Fs_annot_tuples_L:
            if ( tupl[1] == "Input" ):
                valtosorton_tuple_T_L.append( [-1, tupl] )
            elif ( tupl[1] == "0 nM" ) and ( self.settings.get_property( "input_library_for_logos" ) != "input"):
                valtosorton_tuple_T_L.append( [-1, (tupl[0], "Input")] )
            else:
                valtosorton_tuple_T_L.append( [int(tupl[1].split(" ")[0]), tupl] )
        valtosorton_tuple_T_L.sort( key = lambda x: x[0] )

        reads_Fs_annot_tuples_L = [x[1] for x in valtosorton_tuple_T_L]
        return reads_Fs_annot_tuples_L



    def rdir_path(self, *args):
        """ the Results directory """
        return os.path.join(self.settings.get_rdir(), *args)


    def get_barcode_match(self, barcode, barcodes):
        """
        takes a barcode and returns the one it matches (within the
        specified hamming distance
        """
        if barcode in barcodes:
            return barcode
        for barcode_j in barcodes:
            try:
                if RBNS_utils.hamming_N(barcode, barcode_j) <=\
                        self.settings.get_property('mismatches_allowed_in_barcode'):
                        return barcode_j
            except ValueError:
                continue
        return ''


    def get_all_barcode_handles(self):
        """
        returns a dictionary barcode -> file handles for the split reads
        """
        return {
                lib_settings.barcode: open(lib_settings.get_split_reads(), 'w') for\
                    lib_settings in self.settings.iter_lib_settings()}

    def get_all_barcode_handles_wrong_insert_len(self):
        """
        returns a dictionary barcode -> file handles for the split reads that
            have the incorrect insert length
        """
        return {
                lib_settings.barcode: open(lib_settings.get_split_reads_wrong_insert_len(), 'w') for\
                        lib_settings in self.settings.iter_lib_settings()}

    def get_all_barcode_fastq_handles(self):
        """
        returns a dictionary barcode-> file handles for the .fastq of the split reads
        """
        return {
                lib_settings.barcode: gzip.open(lib_settings.get_split_fastqs(), 'wb')
                for lib_settings in self.settings.iter_lib_settings()}



    def get_rdir_fhandle( self, *args ):
        """
        Returns an opened file handle
        """
        out_path = self.rdir_path(*args)
        out_DIR = os.path.dirname( out_path )
        if not os.path.exists( out_DIR ):
            os.makedirs( out_DIR )
        return RBNS_utils.aopen(out_path, 'w')










def count_naive(
        split_reads,
        k,
        out_pkl,
        normalize = False ):
    """
    - Gets the kmer counts in split_reads and stores the result to out_pkl
    """
    print 'Getting read {0}mer counts in {1}\n'.format( k, split_reads )
    counts = np.zeros(4 ** k, dtype=int)
    kmer2index = {}
    for i, kmer in enumerate(RBNS_utils.yield_kmers(k)):
        kmer2index[kmer] = i
    with RBNS_utils.aopen(split_reads) as f:
        read = f.readline()
        read_len = len(read.strip())
        while read:
            if not 'N' in read:
                for ki in range(0, read_len - k + 1):
                    try:
                        kmer_index = kmer2index[read[ki:ki + k]]
                        counts[kmer_index] += 1
                    except:
                        pass
            read = f.readline()
    # if they are normalized, the keys will be kmers instead of indices, and
    # they will be normalized so that the sum of values is 4 ** k
    if (normalize == True):
        total = 0
        for i, kmer in enumerate(RBNS_utils.yield_kmers(k)):
            total += counts[i]
        counts_kmer_keys = {}
        for i, kmer in enumerate(RBNS_utils.yield_kmers(k)):
            counts_kmer_keys[kmer] = counts[i] * float(4 ** k)/total
        counts = counts_kmer_keys
    cPickle.dump(counts, open(out_pkl, 'wb'))




def count_naive_max_once(
        split_reads,
        k,
        out_pkl,
        normalize = False ):
    """
    - Gets the kmer counts in split_reads and stores the result to out_pkl
    """
    print 'Getting read {0}mer counts in {1}\n'.format( k, split_reads )
    counts = np.zeros(4 ** k, dtype=int)
    kmer2index = {}
    for i, kmer in enumerate(RBNS_utils.yield_kmers(k)):
        kmer2index[kmer] = i
    with RBNS_utils.aopen(split_reads) as f:
        read = f.readline()
        read_len = len(read.strip())
        while read:
            if not 'N' in read:
                kis_this_read_S = set()
                for ki in range(0, read_len - k + 1):
                    kmer_index = kmer2index[read[ki:ki + k]]
                    kis_this_read_S.add( kmer_index )
                #### For each ki in this read, add it to counts
                for kmer_index in kis_this_read_S:
                    counts[kmer_index] += 1
            read = f.readline()
    # if they are normalized, the keys will be kmers instead of indices, and
    # they will be normalized so that the sum of values is 4 ** k
    if (normalize == True):
        total = 0
        for i, kmer in enumerate(RBNS_utils.yield_kmers(k)):
            total += counts[i]
        counts_kmer_keys = {}
        for i, kmer in enumerate(RBNS_utils.yield_kmers(k)):
            counts_kmer_keys[kmer] = counts[i] * float(4 ** k)/total
        counts = counts_kmer_keys
    cPickle.dump(counts, open(out_pkl, 'wb'))





def count_by_position(
        split_reads,
        k,
        out_pkl ):
    """
    - Gets the kmer counts by read position in split_reads and stores the result to out_pkl
    """
    print 'Getting read {0}mer counts by position in {1}\n'.format( k, split_reads )

    ### Get the split_reads lengths
    with open( split_reads ) as f:
        for line in f:
            read_len = len( line.strip() )
            break

    counts_by_position_D = {}
    for start_pos in range( read_len - k + 1 ):
        counts_by_position_D[start_pos] = {}
        for kmer in RBNS_utils.yield_kmers(k):
            counts_by_position_D[start_pos][kmer] = 0.

    with RBNS_utils.aopen(split_reads) as f:
        for line in f:
            read = line.strip()
            for start_pos in range( read_len - k + 1 ):
                kmer = read[start_pos:(start_pos+k)]
                try:
                    counts_by_position_D[start_pos][kmer] += 1
                #### Ignore if kmer contain's an N
                except KeyError:
                    pass

    #### pickle the counts dictionary
    with open( out_pkl, 'wb' ) as f:
        cPickle.dump( counts_by_position_D, f )

    #### convert each of the counts into frequencies at each position
    freqs_by_position_D = {}
    for start_pos, counts_D in counts_by_position_D.iteritems():
        freqs_D = RBNS_utils.normalize_D( counts_D )
        freqs_by_position_D[start_pos] = freqs_D

    #### Pickle the frequencies dictionary
    freq_Ds_DIR = os.path.dirname( out_pkl ).replace( "counts/by_position",
            "frequency_Ds" )
    RBNS_utils.make_dir( freq_Ds_DIR )
    freq_D_basename = os.path.basename( out_pkl ).rsplit( "_", 1 )[0] +\
            ".{0}mer.frequencies.by_position.pkl".format( k )
    freq_D_F = os.path.join( freq_Ds_DIR, freq_D_basename )
    with open( freq_D_F, "wb" ) as f:
        cPickle.dump( freqs_by_position_D, f )





def count_stream(
        split_reads,
        k,
        out_pkl,
        passes = 2 ):
    """
    - Does the stream count for the given split reads and k and stores result
    """
    stream_weights = streaming_convergence.stream_counts(
        k, split_reads, passes)
    cPickle.dump( stream_weights, open( out_pkl, 'wb' ))



def get_Zscores_and_from_R_table(
        R_table_F ):
    """
    - Given an enrichment table, make an output enrichment table that
        also includes the Z-scores for each
    """
    #### The out_txt_F that will contain all of the Z-scores
    out_basename = os.path.basename( R_table_F ).rsplit( ".", 1 )[0] + ".w_all_Zscores.txt"
    out_txt_F = os.path.join( os.path.dirname( R_table_F ), out_basename )

    header_L = []
    with open( R_table_F ) as f:
        for line in f:
            header_L = line.strip().split("\t")
            break

    Rs_L_by_libannot_D = {}
    for libannot in header_L[1:]:
        Rs_L_by_libannot_D[libannot] = []
    #### header_L is like:
    ###     ["[IGF2BP1]", "5 nM", "20 nM", "80 nM", "320 nM", "1300 nM"]
    with open( R_table_F ) as f:
        next( f )
        for line in f:
            R_line_L = line.strip().split("\t")
            try:
                assert( len( R_line_L ) == len( header_L ) )
            except AssertionError:
                continue
            for idx, libannot in enumerate( header_L ):
                #### Pass if it's the first column
                if ( idx == 0 ):
                    continue
                Rs_L_by_libannot_D[libannot].append( float( R_line_L[idx] ) )
    #### Now go through an calculate the mean & std R for each library
    mean_and_std_by_libannot_D = {}
    for libannot, Rs_L in Rs_L_by_libannot_D.iteritems():
        mean_R = np.mean( Rs_L )
        std_R = np.std( Rs_L )

        mean_and_std_by_libannot_D[libannot] = {"mean": mean_R, "std_R": std_R}

    #### Now go through and make the out_F
    out_f = open( out_txt_F, "w" )

    #### Write the header line
    out_f.write( header_L[0] + "\t" )
    for col_header in header_L[1:]:
        out_f.write( "{}\tZ\t".format( col_header ) )
    out_f.write( "\n" )
    for idx, libannot in enumerate( header_L ):
        if ( idx > 0 ):
            string = "\tmean R: {0:.3f}\tSt.Dev: {1:.3f}".format(
                    mean_and_std_by_libannot_D[libannot]["mean"],
                    mean_and_std_by_libannot_D[libannot]["std_R"] )
            out_f.write( string )
    out_f.write( "\n" )

    #### Go through each line of the original enrichments_F
    with open( R_table_F ) as f:
        next( f )
        for line in f:
            R_line_L = line.strip().split("\t")
            try:
                assert( len( R_line_L ) == len( header_L ) )
            except AssertionError:
                continue
            for idx, libannot in enumerate( header_L ):
                #### Pass if it's the first column, write out the kmer
                if ( idx == 0 ):
                    out_f.write( R_line_L[idx] )
                else:
                    R = float( R_line_L[idx] )
                    Zscore = RBNS_utils.return_Zscore( R,
                            mean_and_std_by_libannot_D[libannot]["mean"],
                            mean_and_std_by_libannot_D[libannot]["std_R"] )
                    out_str = "\t{0:.3g}\t{1:.3g}".format( R, Zscore )
                    out_f.write( out_str )
            out_f.write( "\n" )
    out_f.close()







def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("settings_file")
    parser.add_argument("--launch-onto-cluster",
                        help = "launches the whole thing on the cluster",
                        action='store_true')
    parser.add_argument("--counts-on-cluster",
            help = "Runs on this node, but submits count jobs to cluster.",
            action = 'store_true' )
    parser.add_argument("--fold",
                        help = "Performs folding (Ppaired) analyses",
                        action='store_true')

    args = parser.parse_args()

    if args.launch_onto_cluster and args.counts_on_cluster:
        print ('Incompatible command line arguments:\n'
               ' Choose either --counts-on-cluster XOR --launch-onto-cluster')
    return args









def launch_on_cluster(args):
    settings_file = os.path.abspath(args.settings_file)
    python_script = os.path.abspath(sys.argv[0])

    assert RBNS_utils.file_exists(settings_file)
    settings = RBNS_settings.RBNS_settings(settings_file)
    error_dir = settings.get_edir()
    RBNS_utils.make_dir( error_dir )
    out_file = os.path.join(error_dir, 'main.out')
    err_file = os.path.join(error_dir, 'main.err')

    assert RBNS_utils.file_exists(python_script)
    assert os.path.exists(error_dir)

    command = ('hostname ; python %(python_script)s'
               ' --counts-on-cluster '
               '%(settings_file)s '
               '1> %(out_file)s '
               '2> %(err_file)s ' % locals())
    protein = settings.get_property('protein_name')
    RBNS_cluster_utils.launch(
        command,
        jobname='%s_RBNS_pipeline' % protein,
        error_dir = error_dir,
        q = 'speedy' )




def main():
    """
    - runs Bnse
    """

    args = parse_args()
    if not RBNS_utils.file_exists( args.settings_file ):
        raise ValueError("Settings file %s doesn't exist" % args.settings_file)
    if args.launch_onto_cluster:
        launch_on_cluster( args )
    else:
        settings = RBNS_settings.RBNS_settings( args.settings_file )
        #b = Bnse(settings, args.counts_on_cluster)
        #### quick should be True (for getting settings), or
        ####    'get_enrichments'
        #b = Bnse(settings, args.counts_on_cluster, quick = 'get_enrichments' )
        b = Bnse( settings, args.counts_on_cluster )








if __name__ == '__main__':
    main()




