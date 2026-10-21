"""Export a chart of LLM atmosphere, unchanged lexicon reference, and usable-data coverage."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--panel',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root/'state') or args.output.exists():
        raise ValueError('출력은 state 아래 새 폴더')
    frame=pd.read_csv(args.panel,dtype={'stock_id':str})
    stocks=sorted(frame.stock_id.unique())
    fig,axes=plt.subplots(3,len(stocks),figsize=(6*len(stocks),9),sharex='col',squeeze=False)
    for i,stock in enumerate(stocks):
        g=frame[frame.stock_id==stock].sort_values('trading_date')
        dates=pd.to_datetime(g.trading_date)
        axes[0,i].plot(dates,g.sentiment_index,label='LLM: eligible related texts',color='#147a73')
        axes[0,i].plot(dates,g.lexicon_sentiment_index,label='Original lexicon',color='#8b94a3',alpha=.8)
        axes[0,i].axhline(0,color='#cccccc',lw=.8)
        axes[0,i].set_ylim(-1.05,1.05);axes[0,i].set_ylabel('Atmosphere (-1 to +1)')
        axes[0,i].set_title(str(g.stock_name.iloc[0]) if str(g.stock_name.iloc[0]).isascii() else f'Stock {stock}')
        axes[0,i].legend(fontsize=8)
        axes[1,i].plot(dates,100*g.close/g.close.iloc[0],color='#3357a2')
        axes[1,i].set_ylabel('Adjusted close (start=100)')
        axes[2,i].bar(dates,g.llm_eligible_share_of_all,width=1.2,color='#b7dbd8')
        axes[2,i].set_ylim(0,1);axes[2,i].set_ylabel('Eligible share of all posts')
        for ax in axes[:,i]:
            ax.grid(alpha=.15);ax.tick_params(axis='x',labelrotation=30)
    fig.suptitle('LLM-estimated forum atmosphere: exploratory, not validated investor sentiment',fontsize=12)
    fig.text(.5,.01,'Gaps indicate insufficient eligible texts. This comparison does not establish causation or predictive value.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.96))
    args.output.mkdir(parents=True,exist_ok=False)
    fig.savefig(args.output/'atmosphere.png',dpi=160)
    fig.savefig(args.output/'atmosphere.svg')
    plt.close(fig)
    print('PNG/SVG 차트 저장 완료')


if __name__=='__main__':
    main()
