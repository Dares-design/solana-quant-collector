import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import os

# Putanja do tvog .db fajla (promeni ime ako je potrebno)
DB_PATH = 'solana_test.db' 

def analyze_token_lifecycle(db_path):
    if not os.path.exists(db_path):
        print(f"Greška: Ne mogu da nađem fajl {db_path}")
        return

    conn = sqlite3.connect(db_path)
    
    # Uzimamo sve podatke iz baze
    query = "SELECT timestamp, symbol, price_usd, liquidity_usd, volume_h24 FROM token_snapshots"
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Pretvaramo vreme u pravi format
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Grupišemo po tokenu i brojimo koliko puta je viđen
    token_counts = df['symbol'].value_counts()
    
    print("\n--- TOP 5 TOKENA KOJE JE BOT NAJDUŽE PRATIO ---")
    print(token_counts.head(5))
    
    # Uzimamo token koji je najduže praćen (osim ako je None)
    target_symbol = token_counts.index[0]
    print(f"\n🔍 Analiziram životni vek tokena: {target_symbol}")
    
    # Filtriramo samo taj token
    token_df = df[df['symbol'] == target_symbol].sort_values('timestamp')
    
    print(f"Prvi put viđen: {token_df['timestamp'].iloc[0]}")
    print(f"Poslednji put viđen: {token_df['timestamp'].iloc[-1]}")
    print(f"Broj snapshota (koliko minuta je praćen): {len(token_df)}")
    
    print(f"Početna cena: ${token_df['price_usd'].iloc[0]}")
    print(f"Krajnja cena: ${token_df['price_usd'].iloc[-1]}")
    
    # Crtamo grafikone
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    # Grafik cene
    ax1.plot(token_df['timestamp'], token_df['price_usd'], color='green', marker='o', markersize=2)
    ax1.set_title(f'Kretanje cene: {target_symbol}')
    ax1.set_ylabel('Cena (USD)')
    ax1.grid(True, alpha=0.3)
    
    # Grafik likvidnosti
    ax2.plot(token_df['timestamp'], token_df['liquidity_usd'], color='blue', marker='o', markersize=2)
    ax2.set_title('Kretanje likvidnosti')
    ax2.set_ylabel('Likvidnost (USD)')
    ax2.set_xlabel('Vreme')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    analyze_token_lifecycle(DB_PATH)