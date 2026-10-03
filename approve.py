"""Separate operator CLI. Never expose as an agent tool."""
import argparse
import json
from control import review_proposal

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('proposal_id');parser.add_argument('--db',default='output/control.db');parser.add_argument('--reviewer',required=True)
    parser.add_argument('--approve',action='store_true',help='Approve the displayed plan after reviewing it in a prior invocation')
    args=parser.parse_args()
    print(json.dumps(review_proposal(args.db,args.proposal_id,args.reviewer,args.approve),indent=2))
if __name__=='__main__':main()
