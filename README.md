
![Logo](img/SHAPEware-logo.png)

***


Welcome to the repository for RNA Bind-N-Seq Analysis! 

SHAPEware is a set of bioinformatics tools to analyze data from high-throughput sequencing experiments that chemically
probe RNA to investigate its structure. In developing SHAPEware, our goal is to create a unified package for all types
of SHAPE data that provides highly accurate and customizable analysis capabilities.


## Installation

##### Requirements

The RBNS pipeline is designed to run on Linux. In addition, it requires the following software to be pre-installed on your computing environment:

- Python (tested on version 2.7.11)
- The [Miniconda](https://conda.io/miniconda.html) or [knaconda](https//docs.anaconda.com/) package manager
- The [forgi](https://viennarna.github.io/forgi/) library.
- The [Weblogo](http://weblogo.threeplusone.com/manual.html) program
- The [RNAfold](https://www.tbi.univie.ac.at/RNA/) program

If you need help installing any of these tools, see the [detailed documentation](docs/installation.md). When installing dependencies, make sure you
agree with the corresponding licenses of various software tools.


## Download and install SHAPEware

The easiest way to get the RBNS pipeline software is to clone our repository. This will ensure you always have access to the latest version. 

	git clone git@bitbucket.org:pfreese/rbns_pipeline.git

After cloning our repository, run the included installation script: 

	cd shapeware
	./install.sh

This will use the Conda package manager to ensure that 
you have all of the key dependencies. This step will create a stable environment in which to run analysis jobs. 
This approach will keep your results reproducible and will not affect other software that you have installed on your system.
While you can also use the RBNS pipeline without this step by installing all necessary packages manually, it is not recommended.


## Test the RBNS pipeline with example data

In this public version, SHAPEware is able to analyze SHAPE-MaP (Smola et al., 2015) data. You can find example input files in the example_data/
directory within the repository. These were derived from experiments that assayed the TPP riboswitch (Haller et al, 2013) in the presence or 
absence of its cognate ligand. 

If you didn't already download the example files with the installation script, run:

	./example_data/download_files.sh 

Once the script has finished running, you can find the output from the software in the example_data/results/ folder.


### SHAPEware-MaP

The inputs to SHAPEware-MaP are described in more detail [here](docs/input_files.md). Here is a quick summary:

- A spreadsheet/CSV file describing the samples (input_sheet.csv) 
- A FASTA file specifying the reference sequences corresponding to the constructs used in SHAPE-MaP (ref_seqs.fa)
- A FASTA file specifying sequence masks (with 'X' characters in positions that should be ignored in downstream analysis) (ref_masks.fa)
- (Optional): a file containing reference 2D structures in dot-bracket notation (ref_structures.dot)

You can find examples of all of these files in the example_data/ folder. It is probably easiest to just take a look at these files first. You can 
run SHAPEware-MaP on this example and reproduce the figures below.

#### Example output: RBFOX3

The output includes several types of files that provide useful visualizations. The most direct output is a plot of
the inferred SHAPE reactivities at each position. For a more detailed description of SHAPE reactivity values, see the paper by 
Smola et al., referenced below. 

SHAPEware analyzes ambiguous and unambiguous mutations to identify positions where SHAPE values may be 
over- or underestimated. These uncertainties are reflected by the thin vertical bars in the following type of plot. 
We are actively investigating error models for SHAPE reactivities that consider read depth, mutation ambiguity and
inter-sample variability. We will post updates here and on the Wiki page as we update these models.

![TPP_shape_bar](img/TPP_shape_values.png)

You can also see the SHAPE reactivity values superimposed on various folding predictions (some made using the SHAPE data as constraints, 
some made while blinded to any SHAPE data).

Presently, SHAPEware integrates with the RNAfold program from the [ViennaRNA suite](https://www.tbi.univie.ac.at/RNA/) and the ShapeKnots program from
David Matthews' [RNAstructure](https://rna.urmc.rochester.edu/RNAstructure.html) package. You can find both types of folds in the output directory.
This example was generated by providing SHAPE values from our example dataset to computationally fold the TPP riboswitch in the absence of TPP ligand. 

![TPP_example](img/TPP_example.png)

Plots are also generated to compare the SHAPE reactivities under the presence or absence of its cognate ligand (or other differential conditions)
and the level of inter-sample variability.

![SHAPE_signal](img/SHAPE_signal_example.png)

You can find the derived SHAPE reactivity values and other useful plots and information in the output/ and plots/ 
subdirectories that are created during the analysis process. The files with the prefix output/agg_reactivity_values are the most direct
place to find the numeric values.

## License

RBNS_pipeline is developed by Peter Freese and released under a GPL v3 license.

## Contact

For any questions or comments about SHAPEware, contact Peter Freese (pfreese [at] mit {dot} edu)

## References

- Lambert, et al. **RNA Bind-n-Seq: quantitative assessment of the sequence and structural binding specificity of RNA binding proteins** _Mol Cell_. 2014 Jun 5;54(5):887-900. doi:  [10.1016/j.molcel.2014.04.016](https://www.ncbi.nlm.nih.gov/pubmed/24837674)
- Lambert, et al. **RNA Bind-n-Seq: quantitative assessment of the sequence and structural binding specificity of RNA binding proteins** _Mol Cell_. 2014 Jun 5;54(5):887-900. doi:  [10.1016/j.molcel.2014.04.016](https://www.ncbi.nlm.nih.gov/pubmed/24837674)
