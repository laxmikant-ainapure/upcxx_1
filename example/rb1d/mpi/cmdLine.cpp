#include <assert.h>
#include <getopt.h>
#include <stdlib.h>
#include <iostream>
#include <mpi.h>
#include "rb1d.h"
using namespace std;


/*
********************************************************************************
*
*
* Parses the parameters from argv
* 
* The following command line flags are available
*
*
*	-n    	<integer>	# pnts
*
*	-i      <integer>	Max # iterations to run
*
*	-e      <double>	convergence threshold
*
*	-f      <integer>	frequency of convergence check
*
*	-p			print convergence data
*
*	-k			Shut off communication
*
********************************************************************************
*/

#define MATCH(s) (!strcmp(argv[arg], (s)))
void PrintUsage(char* program, char* option, int myid);

/* Default values */

const int def_N = 16;
const int def_chk_freq = 100;
const double def_epsilon = 1.0e-3;

void cmdLine(int argc, char *argv[], int& N, double& epsilon, int& chk_freq,
		int& maxIter, bool& printConvg, bool& noComm)
{
   int argcount = argc;
   int myid;
   int arg;
/// Command line arguments
 static struct option long_options[] = {
        {"N", required_argument, NULL, 'N'},
        {"eps", required_argument, NULL, 'e'},
        {"freq", required_argument, NULL, 'f'},
        {"maxiter", required_argument, NULL, 'i'},
        {"print", no_argument, NULL, 'p'},
        {"nocomm", no_argument, NULL, 'k'},
 };


			    /* Fill in default values */
   epsilon = def_epsilon;
   N = def_N;
   chk_freq = def_chk_freq;
   printConvg = false;
   noComm = false;
   maxIter = 0;
   MPI_Comm_rank(MPI_COMM_WORLD,&myid);

   /* Parse the command line arguments -- 
    *if something is not kosher, die
    */
   int ac;
 for(ac=1;ac<argc;ac++) {
    int c;
    while ((c=getopt_long(argc,argv,"n:e:f:i:pk?",long_options,NULL)) != -1){
        switch (c) {

	    // N
            case 'n':
                N = atoi(optarg);
                break;

	    // Epsilon
            case 'e':
                epsilon = atof(optarg);
                break;

	    // Freq
            case 'f':
                chk_freq = atof(optarg);
                break;

	    // Max Iterations
            case 'i':
                maxIter = atoi(optarg);
                break;

            // Print Convergence
            case 'p':
                printConvg = true;
                break;

            // No communication
            case 'k':
                noComm = true;
                break;

	    // Error
            case '?':
	       MPI_Barrier(MPI_COMM_WORLD);
	       if (!myid){
		   cerr << "Error in command line argument: " << optarg << endl;
		   // cerr << "\t-s <integer> max message size (in KB)\n";
	       cerr << flush;
	       }
	       MPI_Barrier(MPI_COMM_WORLD);
               exit(-1);
	       break;

            default:  /* You can't get here */
	       break;
	}
     }
   }
   if (maxIter == 0)
        maxIter = N * N;
}

/*
********************************************************************************
*
*
* Prints out the command line options
*
*
********************************************************************************
*/

void PrintUsage(char* program, char* option, int myid)
  {
    if (!myid)
     {
       fprintf(stderr,"%s : error in argument %s\n", program, option);
       fprintf(stderr, "\t-n <integer> problem size\n");
       fprintf(stderr, "\t-e <double> convergence threshold\n");
       fprintf(stderr, "\t-i <integer> Max Number of Iterations\n");
       fprintf(stderr, "\t-f <integer> convergence check frequency\n");
       fprintf(stderr, "\t-p          print convergence information \n");
       fprintf(stderr, "\t-k          shut off communication\n");
       fflush(NULL);
     }
   MPI_Abort(MPI_COMM_WORLD,-1);
  }