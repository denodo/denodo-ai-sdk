"""
Manages in-memory user storage.
"""

from sample_chatbot.models.user import User

class UserStore:
    """
    In-memory user store.

    Manages user instances for the application.
    Thread-safe for basic operations.
    """

    def __init__(self):
        self._users = {}

    def get(self, user_id):
        """Get a user by ID."""
        return self._users.get(user_id)

    def add(self, user):
        """Add or update a user."""
        self._users[user.id] = user

    def remove(self, user_id):
        """Remove a user by ID."""
        return self._users.pop(user_id, None)

    def exists(self, user_id):
        """Check if a user exists."""
        return user_id in self._users

    def create_user(self, username, password, config):
        """
        Create and store a new user.

        Args:
            username: User's username
            password: User's password
            config: ChatbotConfig instance

        Returns:
            User instance
        """
        user = User(username, password, config)
        self.add(user)
        return user

    def clear(self):
        """Clear all users."""
        self._users.clear()

# Singleton instance
user_store = UserStore()
