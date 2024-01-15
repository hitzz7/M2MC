from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json
import sqlite3
import threading
import cgi
import uuid
import os
from PIL import Image
import mysql.connector


class DatabaseManager:
    def __init__(self, host, user, password, database):
        self.connection_params = {
            'host': host,
            'user': user,
            'password': password,
            'database': database
        }

    def create_tables(self):
        conn = mysql.connector.connect(**self.connection_params)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                is_deleted BOOLEAN DEFAULT 0
                
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL
                
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_category (
                product_id INT,
                category_id INT,
                PRIMARY KEY (product_id, category_id),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT,
                price FLOAT,
                quantity INT,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT,
                image_path TEXT,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')
        

        conn.commit()
        conn.close()

    def execute_query(self, query, values=None, fetch=True):
        with mysql.connector.connect(**self.connection_params) as conn:
            cursor = conn.cursor()
            try:
                if values:
                    cursor.execute(query, values)
                else:
                    cursor.execute(query)

                if 'INSERT' in query.upper():
                    # Return the last inserted ID for INSERT queries
                    last_row_id = cursor.lastrowid
                elif 'UPDATE' in query.upper() or 'DELETE' in query.upper():
                    # Return the number of affected rows for UPDATE and DELETE queries
                    last_row_id = cursor.rowcount
                else:
                    # Fetch or iterate through the results if the query produces any
                    last_row_id = None
                    if fetch:
                        last_row_id = cursor.fetchall()  # or fetchone(), or iterate over cursor

                conn.commit()
                return last_row_id
            finally:
                cursor.close()
    
    def execute_query_many(self, query, values_list):
        with mysql.connector.connect(**self.connection_params) as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, values_list)
                conn.commit()
            finally:
                cursor.close()