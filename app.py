from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

def parse_rank(rank_str):
    match = re.search(r'\[(\d+)([dk])\]', rank_str)
    if not match:
        return None
    number = int(match.group(1))
    letter = match.group(2).lower()
    return number if letter == 'k' else 30 + number

def get_month_links(soup, username):
    month_links = []
    pattern = re.compile(rf'gameArchives\.jsp\?user={re.escape(username)}&year=\d{{4}}&month=\d{{1,2}}')
    for a in soup.find_all('a'):
        href = a.get('href')
        if href and pattern.match(href):
            month_links.append(href)
    return month_links

def parse_matches_from_soup(soup):
    matches = []
    tables = soup.find_all('table')
    if not tables:
        return matches
    table = tables[0]
    for row in table.find_all('tr')[1:]:
        cols = row.find_all('td')
        if len(cols) < 7:
            continue
        match = {
            'viewable_link': cols[0].find('a')['href'] if cols[0].find('a') else '',
            'viewable_text': cols[0].get_text(strip=True),
            'white_text': cols[1].get_text(strip=True),
            'black_text': cols[2].get_text(strip=True),
            'setup': cols[3].get_text(strip=True),
            'start_time': cols[4].get_text(strip=True),
            'type': cols[5].get_text(strip=True),
            'result': cols[6].get_text(strip=True),
        }
        matches.append(match)
    return matches

def remove_duplicate_matches(matches):
    seen = set()
    unique = []
    for m in matches:
        key = m.get('viewable_link', '')
        if key and key not in seen:
            seen.add(key)
            unique.append(m)
    return unique

@app.route('/', methods=['GET', 'POST'])
def index():
    username = ''
    opponent = ''
    stats = {
        'total_wins': 0, 'total_losses': 0, 'white_wins': 0, 'black_wins': 0,
        'wins_vs_higher_rank': 0, 'losses_vs_higher_rank': 0,
        'wins_vs_equal_rank': 0, 'losses_vs_equal_rank': 0,
        'wins_vs_lower_rank': 0, 'losses_vs_lower_rank': 0,
        'wins_vs_unknown_rank': 0, 'losses_vs_unknown_rank': 0,
    }
    h2h_stats = {
        'matches_found': 0, 'player1_wins': 0, 'player1_white_wins': 0, 'player1_black_wins': 0,
        'player2_wins': 0, 'player2_white_wins': 0, 'player2_black_wins': 0,
        'player1_win_pct': 0, 'player2_win_pct': 0
    }

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        opponent = request.form.get('opponent', '').strip()

        if not username:
            return "Du måste ange en användare."

        base_url = "https://www.gokgs.com/"
        url = f"{base_url}gameArchives.jsp?user={username}"
        resp = requests.get(url)
        if resp.status_code != 200:
            return f"Fel vid hämtning: {resp.status_code}"

        soup = BeautifulSoup(resp.text, 'html.parser')
        month_links = get_month_links(soup, username)
        all_matches = parse_matches_from_soup(soup)

        for link in month_links:
            full_url = base_url + link
            resp_month = requests.get(full_url)
            if resp_month.status_code == 200:
                soup_month = BeautifulSoup(resp_month.text, 'html.parser')
                all_matches.extend(parse_matches_from_soup(soup_month))

        matches = remove_duplicate_matches(all_matches)
        username_lower = username.lower()
        opponent_lower = opponent.lower()

        # Filtrera matcher där username är med
        username_matches = [
            m for m in matches
            if username_lower == m['white_text'].split()[0].lower() or
               username_lower == m['black_text'].split()[0].lower()
        ]

        # Räkna statistik för username
        for m in username_matches:
            white_rank = parse_rank(m['white_text'])
            black_rank = parse_rank(m['black_text'])
            res = m['result'].upper()
            white_won = res.startswith('W+')
            black_won = res.startswith('B+')
            white_name = m['white_text'].split()[0].lower()
            black_name = m['black_text'].split()[0].lower()

            if username_lower == white_name:
                won = white_won
                stats['white_wins'] += int(won)
            else:
                won = black_won
                stats['black_wins'] += int(won)

            if won:
                stats['total_wins'] += 1
            else:
                stats['total_losses'] += 1

            player_rank = white_rank if username_lower == white_name else black_rank
            opponent_rank = black_rank if username_lower == white_name else white_rank

            if player_rank is None or opponent_rank is None:
                if won:
                    stats['wins_vs_unknown_rank'] += 1
                else:
                    stats['losses_vs_unknown_rank'] += 1
            elif opponent_rank > player_rank:
                if won:
                    stats['wins_vs_higher_rank'] += 1
                else:
                    stats['losses_vs_higher_rank'] += 1
            elif opponent_rank == player_rank:
                if won:
                    stats['wins_vs_equal_rank'] += 1
                else:
                    stats['losses_vs_equal_rank'] += 1
            else:
                if won:
                    stats['wins_vs_lower_rank'] += 1
                else:
                    stats['losses_vs_lower_rank'] += 1

        # Head-to-Head statistik om opponent angetts
        if opponent:
            h2h_stats['player1'] = username
            h2h_stats['player2'] = opponent

            h2h_matches = [
                m for m in matches
                if {username_lower, opponent_lower} == {
                    m['white_text'].split()[0].lower(),
                    m['black_text'].split()[0].lower()
                }
            ]

            for m in h2h_matches:
                w_name = m['white_text'].split()[0].lower()
                b_name = m['black_text'].split()[0].lower()
                res = m['result'].upper()

                h2h_stats['matches_found'] += 1
                p1_won = (res.startswith('W+') and w_name == username_lower) or (res.startswith('B+') and b_name == username_lower)
                p2_won = (res.startswith('W+') and w_name == opponent_lower) or (res.startswith('B+') and b_name == opponent_lower)

                if p1_won:
                    h2h_stats['player1_wins'] += 1
                    if w_name == username_lower:
                        h2h_stats['player1_white_wins'] += 1
                    else:
                        h2h_stats['player1_black_wins'] += 1
                elif p2_won:
                    h2h_stats['player2_wins'] += 1
                    if w_name == opponent_lower:
                        h2h_stats['player2_white_wins'] += 1
                    else:
                        h2h_stats['player2_black_wins'] += 1

            total = h2h_stats['player1_wins'] + h2h_stats['player2_wins']
            if total > 0:
                h2h_stats['player1_win_pct'] = round(100 * h2h_stats['player1_wins'] / total, 2)
                h2h_stats['player2_win_pct'] = round(100 * h2h_stats['player2_wins'] / total, 2)

    return render_template('index.html', username=username, opponent=opponent,
                           stats=stats, h2h=h2h_stats)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
