import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import os

DB_PATH = 'solana_test.db' 

def analyze_token_lifecycle(db_path):
    if not os.path.exists(db_path):
        print(f"Greška: Ne mogu da nađem fajl {db_path}")
        return

    conn = sqlite3.connect(db_path)
    query = "SELECT * FROM token_snapshots"
    df = pd.read_sql_query(query, conn)
    conn.close()

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    token_counts = df['symbol'].value_counts()
    
    print("\n--- TOP 5 TOKENA KOJE JE BOT NAJDUŽE PRATIO ---")
    print(token_counts.head(5))
    
    target_symbol = token_counts.index[0]
    print(f"\n🔍 Analiziram životni vek tokena: {target_symbol}")
    
    token_df = df[df['symbol'] == target_symbol].sort_values('timestamp').copy()
    
    print(f"Broj snapshota (koliko minuta je praćen): {len(token_df)}")
    
    # Provera da li V2 kolone postoje
    has_v2_data = 'buys_m5' in token_df.columns and token_df['buys_m5'].notna().any()
    
    if has_v2_data:
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    else:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # 1. Grafik cene
    ax1.plot(token_df['timestamp'], token_df['price_usd'], color='green', marker='o', markersize=2)
    ax1.set_title(f'Kretanje cene: {target_symbol}')
    ax1.set_ylabel('Cena (USD)')
    ax1.grid(True, alpha=0.3)
    
    # 2. Grafik likvidnosti
    ax2.plot(token_df['timestamp'], token_df['liquidity_usd'], color='blue', marker='o', markersize=2)
    ax2.set_title('Kretanje likvidnosti')
    ax2.set_ylabel('Likvidnost (USD)')
    ax2.grid(True, alpha=0.3)
    
    # 3. Grafik Buy/Sell pritiska (ako imamo V2 podatke)
    if has_v2_data:
        token_df['buys_m5'] = token_df['buys_m5'].fillna(0)
        token_df['sells_m5'] = token_df['sells_m5'].fillna(0)
        
        ax3.bar(token_df['timestamp'], token_df['buys_m5'], color='green', alpha=0.6, label='Kupovine (M5)')
        ax3.bar(token_df['timestamp'], -token_df['sells_m5'], color='red', alpha=0.6, label='Prodaje (M5)')
        ax3.set_title('Pritisak kupaca (zeleno) vs prodavaca (crveno)')
        ax3.set_ylabel('Broj transakcija')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        ax3.set_xlabel('Vreme')
    else:
        print("\n⚠️ Nema V2 podataka (buys_m5/sells_m5) u ovom fajlu. Učitaj noviji .db fajl.")
        ax2.set_xlabel('Vreme')
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    analyze_token_lifecycle(DB_PATH)