"""
Debug Routes for Database Inspection
Add these routes to your Flask app for easy database inspection during testing.
"""

import os

from flask import Blueprint, jsonify, render_template_string, flash, redirect, url_for
from flask_login import current_user
from modules.extensions import db
from modules.models import (
    Player,
    Match,
    Game,
    Play,
    Pick,
    Draft,
    GameActions,
    Removed,
    CardsPlayed,
    TaskHistory,
    MultifacedCard,
    InputOption,
    AllDeck,
)

debug_bp = Blueprint('debug', __name__, url_prefix='')


def _is_debug_admin_authorized():
    """Allow debug routes for admin users, uid=1, or ADMIN_EMAILS."""
    try:
        if not getattr(current_user, "is_authenticated", False):
            return False
        admin_emails = {
            email.strip().lower()
            for email in os.environ.get("ADMIN_EMAILS", "").split(",")
            if email.strip()
        }
        current_email = (getattr(current_user, "email", "") or "").strip().lower()
        return (
            bool(getattr(current_user, "is_admin", False))
            or (getattr(current_user, "uid", None) == 1)
            or (current_email in admin_emails)
        )
    except Exception:
        return False


@debug_bp.before_request
def _require_debug_admin():
    """Protect all debug routes."""
    if not _is_debug_admin_authorized():
        return jsonify({"error": "Forbidden"}), 403


def _summarize_runtime_loaded_data():
    """Return lightweight summaries of in-memory loaded data from modules.views."""
    summary = {}
    try:
        from modules import views as views_module

        # Populate globals if not already loaded.
        views_module.ensure_data_loaded()

        options = getattr(views_module, "options", None)
        multifaced = getattr(views_module, "multifaced", None)
        all_decks = getattr(views_module, "all_decks", None)

        options_sample = {}
        if isinstance(options, dict):
            for key in list(options.keys())[:3]:
                value = options.get(key, [])
                options_sample[key] = value[:3] if isinstance(value, list) else value

        multifaced_sample = {}
        if isinstance(multifaced, dict):
            for category in list(multifaced.keys())[:2]:
                front_back_map = multifaced.get(category, {})
                if isinstance(front_back_map, dict):
                    sample_pairs = list(front_back_map.items())[:3]
                    multifaced_sample[category] = sample_pairs
                else:
                    multifaced_sample[category] = str(type(front_back_map).__name__)

        all_decks_sample = {}
        if isinstance(all_decks, dict) and all_decks:
            first_month = next(iter(all_decks.keys()))
            month_rows = all_decks.get(first_month, [])
            first_row = month_rows[0] if month_rows else None
            all_decks_sample = {
                "sample_month": first_month,
                "month_entry_count": len(month_rows) if isinstance(month_rows, list) else 0,
                "first_entry_type": type(first_row).__name__ if first_row is not None else None,
                "first_entry_preview": str(first_row)[:300] if first_row is not None else None,
            }

        summary = {
            "options": {
                "type": type(options).__name__,
                "count": len(options) if isinstance(options, dict) else None,
                "sample": options_sample,
            },
            "multifaced": {
                "type": type(multifaced).__name__,
                "count": len(multifaced) if isinstance(multifaced, dict) else None,
                "sample": multifaced_sample,
            },
            "all_decks": {
                "type": type(all_decks).__name__,
                "count": len(all_decks) if isinstance(all_decks, dict) else None,
                "sample": all_decks_sample,
            },
        }
    except Exception as e:
        summary = {"error": str(e)}

    return summary

@debug_bp.route('/db')
def inspect_database():
    """Web interface for database inspection"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MTGO-DB Database Inspector</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .table { margin: 20px 0; padding: 15px; border: 1px solid #ddd; }
            .count { font-weight: bold; color: #007bff; }
            .error { color: #dc3545; }
            .success { color: #28a745; }
            .sample { margin: 10px 0; padding: 10px; background: #f8f9fa; }
            pre { background: #f1f3f4; padding: 10px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <h1>MTGO-DB Database Inspector</h1>
        <p><em>Real-time view of your database contents</em></p>
        
        {% for table_info in tables %}
        <div class="table">
            <h3>{{ table_info.name }}</h3>
            <p>Records: <span class="count">{{ table_info.count }}</span></p>
            
            {% if table_info.error %}
                <p class="error">Error: {{ table_info.error }}</p>
            {% elif table_info.samples %}
                <div class="sample">
                    <strong>Sample records:</strong>
                    <pre>{{ table_info.samples }}</pre>
                </div>
            {% else %}
                <p><em>No records found</em></p>
            {% endif %}
        </div>
        {% endfor %}

        <hr>
        <h2>Loaded Runtime Data (Not DB Rows)</h2>
        <p><em>Current in-memory structures used by app logic.</em></p>
        <pre>{{ runtime_data }}</pre>
        
        <hr>
        <p><strong>Quick Actions:</strong></p>
        <ul>
            <li><a href="/db/json">View as JSON</a></li>
            <li><a href="/db/players">View Players Only</a></li>
            <li><a href="/db/matches">View Matches Only</a></li>
            <li><a href="/db/task_history">View Task History</a></li>
            <li><a href="/db/multifaced_cards">View Multifaced Cards</a></li>
            <li><a href="/db/input_options">View Input Options</a></li>
            <li><a href="/db/all_decks">View All Decks</a></li>
            <li><a href="/recent">View Recent Activity</a></li>
        </ul>
    </body>
    </html>
    """
    
    # Inspect all tables
    models = [
        ("Players", Player),
        ("Matches", Match),
        ("Games", Game),
        ("Plays", Play),
        ("Picks", Pick),
        ("Drafts", Draft),
        ("Game Actions", GameActions),
        ("Removed Games", Removed),
        ("Cards Played", CardsPlayed),
        ("Task History", TaskHistory),
        ("Multifaced Cards", MultifacedCard),
        ("Input Options", InputOption),
        ("All Decks", AllDeck),
    ]
    
    tables = []
    for name, model in models:
        try:
            count = model.query.count()
            samples = ""
            
            if count > 0:
                records = model.query.limit(3).all()
                record_details = []
                for record in records:
                    if hasattr(record, 'as_dict'):
                        # Use as_dict method if available
                        record_data = record.as_dict()
                        formatted = "\n".join([f"  {key}: {value}" for key, value in record_data.items()])
                    else:
                        # For Player model, manually extract fields
                        record_data = {}
                        for column in record.__table__.columns:
                            record_data[column.name] = getattr(record, column.name, None)
                        formatted = "\n".join([f"  {key}: {value}" for key, value in record_data.items()])
                    
                    record_details.append(f"Record {record.uid if hasattr(record, 'uid') else getattr(record, 'task_id', 'ID')}:\n{formatted}")
                
                samples = "\n\n".join(record_details)
                if count > 3:
                    samples += f"\n\n... and {count - 3} more records"
            
            tables.append({
                'name': name,
                'count': count,
                'samples': samples,
                'error': None
            })
        except Exception as e:
            tables.append({
                'name': name,
                'count': 0,
                'samples': "",
                'error': str(e)
            })
    
    runtime_data = _summarize_runtime_loaded_data()
    return render_template_string(html, tables=tables, runtime_data=runtime_data)

@debug_bp.route('/db/json')
def inspect_database_json():
    """JSON API for database inspection"""
    models = [
        ("players", Player),
        ("matches", Match),
        ("games", Game),
        ("plays", Play),
        ("picks", Pick),
        ("drafts", Draft),
        ("game_actions", GameActions),
        ("removed_cards", Removed),
        ("cards_played", CardsPlayed),
        ("task_history", TaskHistory),
        ("multifaced_cards", MultifacedCard),
        ("input_options", InputOption),
        ("all_decks", AllDeck),
    ]
    
    result = {}
    for name, model in models:
        try:
            count = model.query.count()
            result[name] = {
                'count': count,
                'status': 'success'
            }
            
            if count > 0:
                # Get sample records (first 5)
                records = model.query.limit(5).all()
                record_details = []
                for record in records:
                    if hasattr(record, 'as_dict'):
                        record_details.append(record.as_dict())
                    else:
                        # For Player model, manually extract fields
                        record_data = {}
                        for column in record.__table__.columns:
                            record_data[column.name] = getattr(record, column.name, None)
                        record_details.append(record_data)
                result[name]['samples'] = record_details
        except Exception as e:
            result[name] = {
                'count': 0,
                'status': 'error',
                'error': str(e)
            }

    result["runtime_loaded_data"] = _summarize_runtime_loaded_data()
    
    return jsonify(result)

@debug_bp.route('/db/<table_name>')
def inspect_specific_table(table_name):
    """Inspect a specific table"""
    model_map = {
        'players': Player,
        'matches': Match,
        'games': Game,
        'plays': Play,
        'picks': Pick,
        'drafts': Draft,
        'game_actions': GameActions,
        'removed_cards': Removed,
        'cards_played': CardsPlayed,
        'task_history': TaskHistory,
        'multifaced_cards': MultifacedCard,
        'input_options': InputOption,
        'all_decks': AllDeck,
    }
    
    model = model_map.get(table_name.lower())
    if not model:
        return jsonify({'error': f'Unknown table: {table_name}', 'available': list(model_map.keys())}), 404
    
    try:
        count = model.query.count()
        records = model.query.limit(20).all()
        
        record_details = []
        for record in records:
            if hasattr(record, 'as_dict'):
                record_details.append(record.as_dict())
            else:
                # For Player model, manually extract fields
                record_data = {}
                for column in record.__table__.columns:
                    record_data[column.name] = getattr(record, column.name, None)
                record_details.append(record_data)
        
        return jsonify({
            'table': table_name,
            'count': count,
            'records': record_details,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@debug_bp.route('/recent')
def show_recent_activity():
    """Show recent database activity"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Recent Activity - MTGO-DB</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .activity { margin: 20px 0; padding: 15px; border: 1px solid #ddd; }
            .record { margin: 5px 0; padding: 5px; background: #f8f9fa; }
        </style>
    </head>
    <body>
        <h1>🕒 Recent Database Activity</h1>
        
        {% if recent_players %}
        <div class="activity">
            <h3>👥 Recent Players</h3>
            {% for player in recent_players %}
            <div class="record">{{ player }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if recent_matches %}
        <div class="activity">
            <h3>🎮 Recent Matches</h3>
            {% for match in recent_matches %}
            <div class="record">{{ match }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if recent_games %}
        <div class="activity">
            <h3>🎯 Recent Games</h3>
            {% for game in recent_games %}
            <div class="record">{{ game }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if recent_tasks %}
        <div class="activity">
            <h3>📋 Recent Tasks</h3>
            {% for task in recent_tasks %}
            <div class="record">{{ task }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        <hr>
        <p><a href="/db">← Back to Database Inspector</a></p>
    </body>
    </html>
    """
    
    try:
        recent_players = Player.query.order_by(Player.uid.desc()).limit(10).all()
        recent_matches = Match.query.limit(10).all()  # Match doesn't have single ID column
        recent_games = Game.query.limit(10).all()     # Game doesn't have single ID column
        recent_tasks = TaskHistory.query.order_by(TaskHistory.task_id.desc()).limit(10).all()
        
        # Format players with complete data
        formatted_players = []
        for player in recent_players:
            player_data = {}
            for column in player.__table__.columns:
                player_data[column.name] = getattr(player, column.name, None)
            formatted_players.append(f"Player {player.uid}: {player_data}")
        
        # Format matches with complete data
        formatted_matches = []
        for match in recent_matches:
            if hasattr(match, 'as_dict'):
                match_data = match.as_dict()
                formatted_matches.append(f"Match {match.match_id}: {match_data}")
        
        # Format games with complete data
        formatted_games = []
        for game in recent_games:
            if hasattr(game, 'as_dict'):
                game_data = game.as_dict()
                formatted_games.append(f"Game {game.match_id}-{game.game_num}: {game_data}")
        
        # Format tasks with complete data
        formatted_tasks = []
        for task in recent_tasks:
            if hasattr(task, 'as_dict'):
                task_data = task.as_dict()
                formatted_tasks.append(f"Task {task.task_id}: {task_data}")
        
        return render_template_string(html, 
                                    recent_players=formatted_players,
                                    recent_matches=formatted_matches,
                                    recent_games=formatted_games,
                                    recent_tasks=formatted_tasks)
    except Exception as e:
        return f"Error: {str(e)}", 500

@debug_bp.route('/update_vars', methods=['GET'])
def update_vars():
    """Legacy manual refresh route for reference datasets."""
    try:
        from modules import views as views_module
        stats = views_module.refresh_reference_data_cache()
    except Exception as e:
        flash(f'Error loading auxiliary files: {e}', category='error')
    else:
        flash(
            f"Loaded all auxiliary files successfully "
            f"(input_options={stats.get('input_options_categories', 0)}, "
            f"multifaced={stats.get('multifaced_groups', 0)}, "
            f"all_decks={stats.get('all_decks_months', 0)}).",
            category='success'
        )
    return redirect(url_for('views.index'))

@debug_bp.route('/admin/refresh-reference-cache', methods=['POST'])
def manual_refresh_reference_cache():
    """Manually refresh reference caches (admin-only)."""
    try:
        from modules import views as views_module
        stats = views_module.refresh_reference_data_cache()
        return jsonify({
            'success': True,
            'message': 'Reference caches refreshed.',
            'refreshed_at_utc': views_module.datetime.datetime.now(
                views_module.datetime.timezone.utc
            ).isoformat().replace('+00:00', 'Z'),
            'stats': stats,
        }), 200
    except Exception as e:
        try:
            from modules import views as views_module
            views_module.debug_log(f"Error refreshing reference cache: {e}")
        except Exception:
            pass
        return jsonify({'error': 'Failed to refresh reference cache'}), 500

@debug_bp.route('/admin/refresh-vintage-cache', methods=['POST'])
def manual_refresh_vintage_cache():
    """Manually clear vintage response caches (admin-only)."""
    try:
        from modules import views as views_module
        stats = views_module.clear_vintage_response_cache()
        return jsonify({
            'success': True,
            'message': 'Vintage response cache cleared.',
            'stats': stats,
        }), 200
    except Exception as e:
        try:
            from modules import views as views_module
            views_module.debug_log(f"Error clearing vintage response cache: {e}")
        except Exception:
            pass
        return jsonify({'error': 'Failed to clear vintage response cache'}), 500

@debug_bp.route('/view_debug_log')
def view_debug_log():
    """View debug log file."""
    try:
        from modules import views as views_module
        log_file = views_module._get_debug_log_file_path()
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            return f"<pre>{log_content}</pre>"
        return "Debug log file not found."
    except Exception as e:
        return f"Error reading debug log: {e}"

# Instructions for adding to your app:
"""
To use these debug routes, add this to your app.py:

from modules.debug_routes import debug_bp
app.register_blueprint(debug_bp)

Then visit:
- http://localhost:8000/db - Web interface for database inspection
- http://localhost:8000/db/json - JSON API for database data
- http://localhost:8000/recent - Recent activity view
- http://localhost:8000/db/players - View players table
- http://localhost:8000/db/task_history - View task history table
""" 