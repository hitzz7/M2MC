from http.server import BaseHTTPRequestHandler, HTTPServer,SimpleHTTPRequestHandler
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

class CategoryHandler(BaseHTTPRequestHandler):
    db_manager = DatabaseManager(
        host='127.0.0.1',
        user='root',
        password='root',
        database='last'
    )
    db_manager.create_tables()
    
    def _send_response(self, status_code, response_body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(response_body.encode('utf-8'))
        
    

    

    def do_GET(self):
        try:
            if self.path == '/categories':
                # Retrieve all categories from the database
                categories = self.db_manager.execute_query('SELECT * FROM categories')
                
                # Format the response data for all categories
                response_data = [{'id': cat[0], 'name': cat[1]} for cat in categories]
                response_body = json.dumps(response_data)
                self._send_response(200, response_body)
            elif self.path.startswith('/categories/'):
                # Extract category ID from the request path
                category_id = int(self.path.split('/')[2])

                # Retrieve category details from the database
                query = 'SELECT * FROM categories WHERE id = %s'
                values = (category_id,)

                # Fetch the results for SELECT queries
                result = self.db_manager.execute_query(query, values, fetch=True)

                # Check if the category with the specified ID exists
                if result and len(result) > 0:
                    category_details = {'id': result[0][0], 'name': result[0][1]}
                    response_body = json.dumps(category_details)
                    self._send_response(200, response_body)
                else:
                    self._send_response(404, 'Category not found')
            else:
                self._send_response(404, 'Not Found')
        except Exception as e:
            print(f"Error handling GET request: {e}")
            self._send_response(500, 'Internal Server Error')


                
    
    

    def do_POST(self):
        if self.path == '/categories':
            content_length = int(self.headers['Content-Length'])
            category_data = json.loads(self.rfile.read(content_length).decode('utf-8'))

            # Assuming category_data is a dictionary with a 'name' key
            query = 'INSERT INTO categories (name) VALUES (%s)'
            values = (category_data.get('name'),)
            
            # Execute the query and get the assigned ID
            new_category_id = self.db_manager.execute_query(query, values)
            
            # Directly access the 'new_category_id' without fetching additional results
            response_body = json.dumps({'id': new_category_id, 'name': category_data.get('name')})
            self._send_response(201, response_body)
        else:
            self._send_response(404, 'Not Found')
            
    def do_PUT(self):
        if self.path.startswith('/categories/'):
            try:
                
                category_id = int(self.path.split('/')[2])

                # Parse the request body to get the updated category data
                content_length = int(self.headers['Content-Length'])
                updated_category_data = json.loads(self.rfile.read(content_length).decode('utf-8'))

                # Check if the 'name' field is provided in the updated data
                if 'name' not in updated_category_data:
                    self._send_response(400, 'Bad Request: Category name is required.')
                    return

                # Update the category in the database
                query = 'UPDATE categories SET name = %s WHERE id = %s'
                values = (updated_category_data['name'], category_id)
                affected_rows = self.db_manager.execute_query(query, values)

                if affected_rows > 0:
                    response_body = json.dumps({'id': category_id, 'name': updated_category_data['name']})
                    self._send_response(200, response_body)
                else:
                    self._send_response(404, 'Category not found')
            except Exception as e:
                print(f"Error updating category: {e}")
                self._send_response(500, 'Internal Server Error')
        else:
            self._send_response(404, 'Not Found')

    def delete_category(self, category_id, soft_delete=False):
        try:
            if soft_delete:
                # Soft delete the category in the database
                query = 'UPDATE categories SET is_deleted = 1 WHERE id = %s'
            else:
                # Hard delete the category from the database
                query = 'DELETE FROM categories WHERE id = %s'

            values = (category_id,)
            affected_rows = self.db_manager.execute_query(query, values)

            if affected_rows > 0:
                self._send_response(200, 'delete completed')  # 204 No Content for successful delete
            else:
                self._send_response(404, 'Category not found')
        except Exception as e:
            print(f"Error deleting category: {e}")
            self._send_response(500, 'Internal Server Error')

    def do_DELETE(self):
        if self.path.startswith('/categories/'):
            category_id = int(self.path.split('/')[2])
            self.delete_category(category_id, soft_delete=False)
        elif self.path.startswith('/categories_soft/'):
            category_id = int(self.path.split('/')[2])
            self.delete_category(category_id, soft_delete=True)
        else:
            self._send_response(404, 'Not Found')



class ProductHandler(BaseHTTPRequestHandler):
    db_manager = DatabaseManager(
        host='127.0.0.1',
        user='root',
        password='root',
        database='last'
    )
    db_manager.create_tables()

    def _send_response(self, status_code, response_body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(response_body.encode('utf-8'))

    def do_GET(self):
        if self.path == '/products':
            try:
                # Fetch product, category, price, and image information for all products
                query = '''
                    SELECT
                        p.id AS product_id,
                        p.name AS product_name,
                        GROUP_CONCAT(DISTINCT pc.category_id) AS category_ids,
                        (SELECT JSON_ARRAYAGG(JSON_OBJECT("price", price, "quantity", quantity))
                        FROM prices pr
                        WHERE pr.product_id = p.id) AS prices,
                        JSON_ARRAYAGG(JSON_OBJECT("image_id", i.id, "image_path", i.image_path)) AS images
                    FROM
                        products p
                    LEFT JOIN
                        product_category pc ON p.id = pc.product_id
                    LEFT JOIN
                        prices pr ON p.id = pr.product_id
                    LEFT JOIN
                        images i ON p.id = i.product_id
                    GROUP BY
                        p.id, p.name
                '''
                products = self.db_manager.execute_query(query, fetch=True)

                response_data = []
                for prod in products:
                    product_info = {
                        'id': prod[0],
                        'name': prod[1],
                        'category_ids': [int(category_id) for category_id in prod[2].split(',')] if prod[2] else [],
                        'prices': json.loads(prod[3]) if prod[3] else [],
                        'images': []
                    }

                    # Process image information and get thumbnails
                    if prod[4]:
                        images = json.loads(prod[4])
                        for img in images:
                            image_id = img.get('image_id')
                            image_path = img.get('image_path')

                            if image_path:  # Check if image path is not None
                                image_info = {
                                    'image_id': image_id,
                                    'image_path': image_path.replace('\\', '/'),
                                    'thumbnail': self._get_thumbnail_path(image_path).replace('\\', '/'),
                                    'thumbnail400': self._get_thumbnail_path400(image_path).replace('\\', '/'),
                                    'thumbnail1200': self._get_thumbnail_path1200(image_path).replace('\\', '/')
                                }
                                product_info['images'].append(image_info)

                    response_data.append(product_info)

                response_body = json.dumps(response_data)
                self._send_response(200, response_body)
            except Exception as e:
                print(f"Error retrieving products: {e}")
                self._send_response(500, 'Internal Server Error')
        elif self.path.startswith('/products/'):
            try:
                # Extract product ID from the request path
                product_id = int(self.path.split('/')[2])

                # Fetch details for the specific product based on ID
                query_single_product = '''
                    SELECT
                        p.id AS product_id,
                        p.name AS product_name,
                        GROUP_CONCAT(DISTINCT pc.category_id) AS category_ids,
                        (SELECT JSON_ARRAYAGG(JSON_OBJECT("price", price, "quantity", quantity))
                        FROM prices pr
                        WHERE pr.product_id = p.id) AS prices,
                        JSON_ARRAYAGG(JSON_OBJECT("image_id", i.id, "image_path", i.image_path)) AS images
                    FROM
                        products p
                    LEFT JOIN
                        product_category pc ON p.id = pc.product_id
                    LEFT JOIN
                        prices pr ON p.id = pr.product_id
                    LEFT JOIN
                        images i ON p.id = i.product_id
                    WHERE
                        p.id = %s
                    GROUP BY
                        p.id, p.name
                '''
                single_product = self.db_manager.execute_query(query_single_product, (product_id,), fetch=True)

                if single_product:
                    product_info = {
                        'id': single_product[0][0],
                        'name': single_product[0][1],
                        'category_ids': [int(category_id) for category_id in single_product[0][2].split(',')] if single_product[0][2] else [],
                        'prices': json.loads(single_product[0][3]) if single_product[0][3] else [],
                        'images': []
                    }

                    # Process image information and get thumbnails
                    if single_product[0][4]:
                        images = json.loads(single_product[0][4])
                        for img in images:
                            image_id = img.get('image_id')
                            image_path = img.get('image_path')

                            if image_path:  # Check if image path is not None
                                image_info = {
                                    'image_id': image_id,
                                    'image_path': image_path.replace('\\', '/'),
                                    'thumbnail': self._get_thumbnail_path(image_path).replace('\\', '/'),
                                    'thumbnail400': self._get_thumbnail_path400(image_path).replace('\\', '/'),
                                    'thumbnail1200': self._get_thumbnail_path1200(image_path).replace('\\', '/')
                                }
                                product_info['images'].append(image_info)

                    response_body = json.dumps(product_info)
                    self._send_response(200, response_body)
                else:
                    self._send_response(404, 'Product not found')
            except Exception as e:
                print(f"Error retrieving product details: {e}")
                self._send_response(500, 'Internal Server Error')
        else:
            self._send_response(404, 'Not Found')



    def do_POST(self):
        if self.path == '/products':
            try:
                content_length = int(self.headers['Content-Length'])
                product_data = json.loads(self.rfile.read(content_length).decode('utf-8'))

                # Validate required fields
                if 'name' not in product_data or 'category_ids' not in product_data or 'prices' not in product_data:
                    self._send_response(400, 'Bad Request: Product name, category_ids, and prices are required.')
                    return

                product_name = product_data['name']
                category_ids = product_data['category_ids']
                prices = product_data['prices']
                
                if not self._categories_exist(category_ids):
                    self._send_response(400, 'Invalid category_id provided')
                    return


                # Insert product into products table
                query_product = 'INSERT INTO products (name) VALUES (%s)'
                values_product = (product_name,)
                product_id = self.db_manager.execute_query(query_product, values_product)

                # Insert categories into product_category table within a transaction
                try:
                    query_category = 'INSERT INTO product_category (product_id, category_id) VALUES (%s, %s)'
                    values_category = [(product_id, category_id) for category_id in category_ids]
                    self.db_manager.execute_query_many(query_category, values_category)
                except Exception as e:
                    # Rollback the transaction on error
                    self.db_manager.execute_query('ROLLBACK')
                    self._send_response(500, f'Internal Server Error: {str(e)}')
                    return

                # Insert prices into the prices table within a transaction
                try:
                    query_price = 'INSERT INTO prices (product_id, price, quantity) VALUES (%s, %s, %s)'
                    values_price = [(product_id, price_data['price'], price_data['quantity']) for price_data in prices]
                    self.db_manager.execute_query_many(query_price, values_price)
                except Exception as e:
                    # Rollback the transaction on error
                    self.db_manager.execute_query('ROLLBACK')
                    self._send_response(500, f'Internal Server Error: {str(e)}')
                    return

                # Commit the transaction
                self.db_manager.execute_query('COMMIT')

                # Create the response body
                response_body = {
                    'id': product_id,
                    'name': product_name,
                    'category_ids': category_ids,
                    'prices': prices,
                }

                # Send the response
                self._send_response(201, json.dumps(response_body))
            except Exception as e:
                print(f"Error processing POST request: {e}")
                self._send_response(500, 'Internal Server Error')
        else:
            self._send_response(404, 'Not Found')
            
    def _categories_exist(self, category_ids):
        # Check if all categories with the provided IDs exist in the database
        for category_id in category_ids:
            query = 'SELECT * FROM categories WHERE id = %s'
            values = (category_id,)
            result = self.db_manager.execute_query(query, values, fetch=True)

            if not result:
                return False  # No category found with the given ID

        return True
            
    def do_PUT(self):
        if self.path.startswith('/products/'):
            try:
                # Extract product ID from the request path
                product_id = int(self.path.split('/')[2])

                # Check if the product with the given ID exists
                if not self._check_product_existence(product_id):
                    self._send_response(404, 'Not Found: Product not found')
                    return

                content_length = int(self.headers['Content-Length'])
                product_data = json.loads(self.rfile.read(content_length).decode('utf-8'))

                # Validate required fields
                if 'name' not in product_data or 'category_ids' not in product_data or 'prices' not in product_data:
                    self._send_response(400, 'Bad Request: Product name, category_ids, and prices are required.')
                    return

                product_name = product_data['name']
                category_ids = product_data['category_ids']
                prices = product_data['prices']
                
                if not self._categories_exist(category_ids):
                    self._send_response(400, 'Invalid category_id provided')
                    return


                # Update product in products table
                query_product = 'UPDATE products SET name = %s WHERE id = %s'
                values_product = (product_name, product_id)
                self.db_manager.execute_query(query_product, values_product)

                # Delete existing categories for the product
                query_delete_categories = 'DELETE FROM product_category WHERE product_id = %s'
                self.db_manager.execute_query(query_delete_categories, (product_id,))

                # Insert categories into product_category table within a transaction
                try:
                    query_category = 'INSERT INTO product_category (product_id, category_id) VALUES (%s, %s)'
                    values_category = [(product_id, category_id) for category_id in category_ids]
                    self.db_manager.execute_query_many(query_category, values_category)
                except Exception as e:
                    # Rollback the transaction on error
                    self.db_manager.execute_query('ROLLBACK')
                    self._send_response(500, f'Internal Server Error: {str(e)}')
                    return

                # Delete existing prices for the product
                query_delete_prices = 'DELETE FROM prices WHERE product_id = %s'
                self.db_manager.execute_query(query_delete_prices, (product_id,))

                # Insert prices into the prices table within a transaction
                try:
                    query_price = 'INSERT INTO prices (product_id, price, quantity) VALUES (%s, %s, %s)'
                    values_price = [(product_id, price_data['price'], price_data['quantity']) for price_data in prices]
                    self.db_manager.execute_query_many(query_price, values_price)
                except Exception as e:
                    # Rollback the transaction on error
                    self.db_manager.execute_query('ROLLBACK')
                    self._send_response(500, f'Internal Server Error: {str(e)}')
                    return

                # Commit the transaction
                self.db_manager.execute_query('COMMIT')

                # Create the response body
                response_body = {
                    'id': product_id,
                    'name': product_name,
                    'category_ids': category_ids,
                    'prices': prices,
                }

                # Send the response
                self._send_response(200, json.dumps(response_body))
            except Exception as e:
                print(f"Error processing PUT request: {e}")
                self._send_response(500, 'Internal Server Error')
        else:
            self._send_response(404, 'Not Found')

    def _check_product_existence(self, product_id):
        # Check if the product with the given ID exists
        query_check_product = 'SELECT id FROM products WHERE id = %s'
        result = self.db_manager.execute_query(query_check_product, (product_id,), fetch=True)
        return bool(result)


    def do_DELETE(self):
        if self.path.startswith('/products/'):
            try:
                # Extract product ID from the request path
                product_id = int(self.path.split('/')[2])

                # Delete the product from the database
                query = 'DELETE FROM products WHERE id = %s'
                values = (product_id,)
                affected_rows = self.db_manager.execute_query(query, values)

                if affected_rows > 0:
                    self._send_response(204, 'delete completed')  # 204 No Content for successful deletion
                else:
                    self._send_response(404, 'Product not found')
            except Exception as e:
                print(f"Error deleting product: {e}")
                self._send_response(500, 'Internal Server Error')
        else:
            self._send_response(404, 'Not Found')

    # Helper functions
    
            
    def _get_thumbnail_path(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        thumbnail_directory = os.path.join(os.path.dirname(original_image_path), 'thumbnails')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
    def _get_thumbnail_path400(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        image_directory = 'images'
        thumbnail_directory = os.path.join(image_directory, 'thumbnail400')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail400_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
    def _get_thumbnail_path1200(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        image_directory = 'images'
        thumbnail_directory = os.path.join(image_directory, 'thumbnail1200')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail1200_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
            
class ImageHandler(BaseHTTPRequestHandler):
    db_manager = DatabaseManager(
        host='127.0.0.1',
        user='root',
        password='root',
        database='last'
    )
    db_manager.create_tables()
    def _send_response(self, status_code, response_body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(response_body.encode('utf-8'))
        
    def do_GET(self):
        if self.path == '/images':
            images = self.db_manager.execute_query('SELECT * FROM images')
            response_data = []

            for img in images:
                image_path = img[2].replace('\\', '/')
                thumbnail_path = self._get_thumbnail_path(img[2]).replace('\\', '/')
                thumbnail_path400 = self._get_thumbnail_path400(img[2]).replace('\\', '/')
                thumbnail_path1200 = self._get_thumbnail_path1200(img[2]).replace('\\', '/')
                image_info = {
                    'id': img[0],
                    'product_id': img[1],
                    'image': image_path,
                    'thumbnail': thumbnail_path,
                    'thumbnail400':thumbnail_path400,
                    'thumbnail1200':thumbnail_path1200
                }
                response_data.append(image_info)

            response_body = json.dumps(response_data)
            self._send_response(200, response_body)
        else:
            self._send_response(404, 'Not Found')
        
    def do_POST(self):
        if self.path == '/images':
            content_type, _ = cgi.parse_header(self.headers['Content-Type'])

            # Check if the request is sending 'multipart/form-data'
            if content_type == 'multipart/form-data':
                form_data = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST',
                             'CONTENT_TYPE': self.headers['Content-Type']}
                )

                # Extract image and product_id from the form data
                image_file = form_data['image'].file
                product_id = form_data.getvalue('product_id')

                # Save the image to a file
                

                # Insert image information into the database
                query = 'INSERT INTO images (product_id, image_file) VALUES (%s, %s)'
                values = (product_id, image_file)
                self.db_manager.execute_query(query, values)

                self._send_response(201, 'Image uploaded successfully')
            else:
                self._send_response(400, 'Invalid Content-Type. Expected multipart/form-data')
        else:
            self._send_response(404, 'Not Found')
            
    def do_PUT(self):
        if self.path.startswith('/images/'):
            image_id = int(self.path.split('/')[2])

            content_type, _ = cgi.parse_header(self.headers['Content-Type'])

            # Check if the request is sending 'multipart/form-data'
            if content_type == 'multipart/form-data':
                form_data = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'PUT',
                            'CONTENT_TYPE': self.headers['Content-Type']}
                )

                # Extract image and product_id from the form data
                image_file = form_data['image'].file
                product_id = form_data.getvalue('product_id')

                # Save the updated image to a file
                image_path = self._save_image_and_thumbnail(image_file)

                # Update image information in the database
                query = 'UPDATE images SET product_id = %s, image_path = %s WHERE id = %s'
                values = (product_id, image_path, image_id)

                try:
                    affected_rows = self.db_manager.execute_query(query, values)
                    if affected_rows > 0:
                        self._send_response(200, 'Image updated successfully')
                    else:
                        self._send_response(404, 'Image not found')
                except Exception as e:
                    print(f"Error updating image: {e}")
                    self._send_response(500, 'Internal Server Error')
            else:
                self._send_response(400, 'Invalid Content-Type. Expected multipart/form-data')
        else:
            self._send_response(404, 'Not Found')

    def do_DELETE(self):
        if self.path.startswith('/images/'):
            image_id = int(self.path.split('/')[2])

            # Delete image by ID
            query = 'DELETE FROM images WHERE id = %s'
            values = (image_id,)

            try:
                affected_rows = self.db_manager.execute_query(query, values)
                if affected_rows > 0:
                    self._send_response(204, '')  # 204 No Content for successful deletion
                else:
                    self._send_response(404, 'Image not found')
            except Exception as e:
                print(f"Error deleting image: {e}")
                self._send_response(500, 'Internal Server Error')
        else:
            self._send_response(404, 'Not Found')


# Add a helper method to check if the image ID exists in the database
    def _image_exists(self, image_id):
        query = 'SELECT id FROM images WHERE id = %s'
        values = (image_id,)
        result = self.db_manager.execute_query(query, values).fetchone()
        return result is not None

    def _save_image_and_thumbnail(self, image_file):
        # Specify the directory where you want to save the images
        image_directory = 'images'

        # Specify the subdirectory "thumbnails" inside the "images" directory
        thumbnail_directory = os.path.join(image_directory, 'thumbnails')
        thumbnail400_directory = os.path.join(image_directory, 'thumbnail400')
        thumbnail1200_directory = os.path.join(image_directory, 'thumbnail1200')

        # Create the directories if they don't exist
        os.makedirs(image_directory, exist_ok=True)
        os.makedirs(thumbnail_directory, exist_ok=True)
        os.makedirs(thumbnail400_directory, exist_ok=True)
        os.makedirs(thumbnail1200_directory, exist_ok=True)

        # Generate unique filenames for the image and thumbnail
        image_filename = f'image_{uuid.uuid4().hex}.png'
        thumbnail_filename = f'thumbnail_{uuid.uuid4().hex}.png'
        thumbnail400_filename = f'thumbnail400_{uuid.uuid4().hex}.png'
        thumbnail1200_filename = f'thumbnail1200_{uuid.uuid4().hex}.png'

        # Construct the full paths to save the image and thumbnail
        image_path = image_filename
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)
        thumbnail400_path = os.path.join(thumbnail400_directory, thumbnail400_filename)
        thumbnail1200_path = os.path.join(thumbnail1200_directory, thumbnail1200_filename)

        # Save the image to the specified path
        with open(image_path, 'wb') as f:
            f.write(image_file.read())

        # Create the thumbnail and save it inside the "thumbnails" directory
        self._create_thumbnail(image_path, thumbnail_path)
        self._create_thumbnail400(image_path, thumbnail400_path)
        self._create_thumbnail1200(image_path, thumbnail1200_path)

        return image_path

    def _create_thumbnail(self, original_image_path, thumbnail_path):
        # Open the original image
        original_image = Image.open(original_image_path)

        # Create a thumbnail with a maximum size of 100x100 pixels
        thumbnail_size = (100, 100)
        thumbnail_image = original_image.copy()
        thumbnail_image.thumbnail(thumbnail_size)

        # Save the thumbnail to the specified path
        thumbnail_image.save(thumbnail_path)
        
    def _create_thumbnail400(self, original_image_path, thumbnail_path):
        # Open the original image
        original_image = Image.open(original_image_path)

        # Create a thumbnail with a maximum size of 100x100 pixels
        thumbnail_size = (400, 400)
        thumbnail_image = original_image.copy()
        thumbnail_image.thumbnail(thumbnail_size)

        # Save the thumbnail to the specified path
        thumbnail_image.save(thumbnail_path)
        
    def _create_thumbnail1200(self, original_image_path, thumbnail_path):
        # Open the original image
        original_image = Image.open(original_image_path)

        # Create a thumbnail with a maximum size of 100x100 pixels
        thumbnail_size = (1200, 1200)
        thumbnail_image = original_image.copy()
        thumbnail_image.thumbnail(thumbnail_size)

        # Save the thumbnail to the specified path
        thumbnail_image.save(thumbnail_path)
        
    def _get_thumbnail_path(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        image_directory = 'images'
        thumbnail_directory = os.path.join(image_directory, 'thumbnails')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
    def _get_thumbnail_path400(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        image_directory = 'images'
        thumbnail_directory = os.path.join(image_directory, 'thumbnail400')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail400_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
    def _get_thumbnail_path1200(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        image_directory = 'images'
        thumbnail_directory = os.path.join(image_directory, 'thumbnail1200')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail1200_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
            
            

    
            
class CustomHandler(SimpleHTTPRequestHandler):
    db_manager = DatabaseManager(
        host='127.0.0.1',
        user='root',
        password='root',
        database='last'
    )
    db_manager.create_tables()
    
    def _send_response(self, status_code, response_body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(response_body.encode('utf-8'))
        
    def do_GET(self):
        if self.path.startswith('/category'):
            # Handle category requests
            # You can implement the category-specific logic here
            categories = self.db_manager.execute_query('SELECT * FROM categories')
                
                # Format the response data for all categories
            response_data = [{'id': cat[0], 'name': cat[1]} for cat in categories]
            response_body = json.dumps(response_data)
            self._send_response(200, response_body)
                
        elif self.path.startswith('/product'):
            # Handle product requests
            # You can implement the product-specific logic here
            query = '''
                SELECT
                    p.id AS product_id,
                    p.name AS product_name,
                    GROUP_CONCAT(DISTINCT pc.category_id) AS category_ids,
                    (SELECT JSON_ARRAYAGG(JSON_OBJECT("price", price, "quantity", quantity))
                    FROM prices pr
                    WHERE pr.product_id = p.id) AS prices,
                    (SELECT JSON_ARRAYAGG(JSON_OBJECT("image_id", image_id, "image_path", image_path))
                    FROM (
                        SELECT DISTINCT i.id AS image_id, i.image_path
                        FROM images i
                        WHERE p.id = i.product_id
                    ) AS distinct_images) AS images
                FROM
                    products p
                LEFT JOIN
                    product_category pc ON p.id = pc.product_id
                LEFT JOIN
                    prices pr ON p.id = pr.product_id
                LEFT JOIN
                    images i ON p.id = i.product_id
                GROUP BY
                    p.id, p.name
            '''
            products = self.db_manager.execute_query(query, fetch=True)

            response_data = []
            for prod in products:
                product_info = {
                    'id': prod[0],
                    'name': prod[1],
                    'category_ids': [int(category_id) for category_id in prod[2].split(',')] if prod[2] else [],
                    'prices': json.loads(prod[3]) if prod[3] else [],
                    'images': []
                }

                # Process image information and get thumbnails
                if prod[4]:
                    images = json.loads(prod[4])
                    for img in images:
                        image_id = img.get('image_id')
                        image_path = img.get('image_path')

                        if image_path:  # Check if image path is not None
                            image_info = {
                                'image_id': image_id,
                                'image_path': image_path.replace('\\', '/'),
                                'thumbnail': self._get_thumbnail_path(image_path).replace('\\', '/'),
                                'thumbnail400': self._get_thumbnail_path400(image_path).replace('\\', '/'),
                                'thumbnail1200': self._get_thumbnail_path1200(image_path).replace('\\', '/')
                            }
                            product_info['images'].append(image_info)

                response_data.append(product_info)

            response_body = json.dumps(response_data)
            self._send_response(200, response_body)
                
        elif self.path.startswith('/image'):
            # Handle image requests
            # You can implement the image-specific logic here
            images = self.db_manager.execute_query('SELECT * FROM images')
            response_data = []

            for img in images:
                image_path = img[2].replace('\\', '/')
                thumbnail_path = self._get_thumbnail_path(img[2]).replace('\\', '/')
                thumbnail_path400 = self._get_thumbnail_path400(img[2]).replace('\\', '/')
                thumbnail_path1200 = self._get_thumbnail_path1200(img[2]).replace('\\', '/')
                image_info = {
                    'id': img[0],
                    'product_id': img[1],
                    'image': image_path,
                    'thumbnail': thumbnail_path,
                    'thumbnail400':thumbnail_path400,
                    'thumbnail1200':thumbnail_path1200
                }
                response_data.append(image_info)

            response_body = json.dumps(response_data)
            self._send_response(200, response_body)
        else:
            # Handle other requests (if needed)
            super().do_GET()
            
    def do_POST(self):
        

        if self.path.startswith('/category'):
            content_length = int(self.headers['Content-Length'])
            category_data = json.loads(self.rfile.read(content_length).decode('utf-8'))

            # Assuming category_data is a dictionary with a 'name' key
            query = 'INSERT INTO categories (name) VALUES (%s)'
            values = (category_data.get('name'),)
            
            # Execute the query and get the assigned ID
            new_category_id = self.db_manager.execute_query(query, values)
            
            # Directly access the 'new_category_id' without fetching additional results
            response_body = json.dumps({'id': new_category_id, 'name': category_data.get('name')})
            self._send_response(201, response_body)
            
        elif self.path.startswith('/product'):
            try:
                content_length = int(self.headers['Content-Length'])
                product_data = json.loads(self.rfile.read(content_length).decode('utf-8'))

                # Validate required fields
                if 'name' not in product_data or 'category_ids' not in product_data or 'prices' not in product_data:
                    self._send_response(400, 'Bad Request: Product name, category_ids, and prices are required.')
                    return

                product_name = product_data['name']
                category_ids = product_data['category_ids']
                prices = product_data['prices']
                
                if not self._categories_exist(category_ids):
                    self._send_response(400, 'Invalid category_id provided')
                    return


                # Insert product into products table
                query_product = 'INSERT INTO products (name) VALUES (%s)'
                values_product = (product_name,)
                product_id = self.db_manager.execute_query(query_product, values_product)

                # Insert categories into product_category table within a transaction
                try:
                    query_category = 'INSERT INTO product_category (product_id, category_id) VALUES (%s, %s)'
                    values_category = [(product_id, category_id) for category_id in category_ids]
                    self.db_manager.execute_query_many(query_category, values_category)
                except Exception as e:
                    # Rollback the transaction on error
                    self.db_manager.execute_query('ROLLBACK')
                    self._send_response(500, f'Internal Server Error: {str(e)}')
                    return

                # Insert prices into the prices table within a transaction
                try:
                    query_price = 'INSERT INTO prices (product_id, price, quantity) VALUES (%s, %s, %s)'
                    values_price = [(product_id, price_data['price'], price_data['quantity']) for price_data in prices]
                    self.db_manager.execute_query_many(query_price, values_price)
                except Exception as e:
                    # Rollback the transaction on error
                    self.db_manager.execute_query('ROLLBACK')
                    self._send_response(500, f'Internal Server Error: {str(e)}')
                    return

                # Commit the transaction
                self.db_manager.execute_query('COMMIT')

                # Create the response body
                response_body = {
                    'id': product_id,
                    'name': product_name,
                    'category_ids': category_ids,
                    'prices': prices,
                }

                # Send the response
                self._send_response(201, json.dumps(response_body))
            except Exception as e:
                print(f"Error processing POST request: {e}")
                self._send_response(500, 'Internal Server Error')
           
        elif self.path.startswith('/image'):
            content_type, _ = cgi.parse_header(self.headers['Content-Type'])

            # Check if the request is sending 'multipart/form-data'
            if content_type == 'multipart/form-data':
                form_data = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST',
                             'CONTENT_TYPE': self.headers['Content-Type']}
                )

                # Extract image and product_id from the form data
                image_file = form_data['image'].file
                product_id = form_data.getvalue('product_id')

                # Save the image to a file
                image_path = self._save_image_and_thumbnail(image_file)

                # Insert image information into the database
                query = 'INSERT INTO images (product_id, image_path) VALUES (%s, %s)'
                values = (product_id, image_path)
                self.db_manager.execute_query(query, values)

                self._send_response(201, 'Image uploaded successfully')
            else:
                self._send_response(400, 'Invalid Content-Type. Expected multipart/form-data')
        
            
        else:
            # Handle other POST requests (if needed)
            pass
            
    def _get_thumbnail_path(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        image_directory = 'images'
        thumbnail_directory = os.path.join(image_directory, 'thumbnails')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
    def _categories_exist(self, category_ids):
        # Check if all categories with the provided IDs exist in the database
        for category_id in category_ids:
            query = 'SELECT * FROM categories WHERE id = %s'
            values = (category_id,)
            result = self.db_manager.execute_query(query, values, fetch=True)

            if not result:
                return False  # No category found with the given ID

        return True
    
    def _check_product_existence(self, product_id):
        # Check if the product with the given ID exists
        query_check_product = 'SELECT id FROM products WHERE id = %s'
        result = self.db_manager.execute_query(query_check_product, (product_id,), fetch=True)
        return bool(result)
    
    def _get_thumbnail_path400(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        image_directory = 'images'
        thumbnail_directory = os.path.join(image_directory, 'thumbnail400')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail400_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
    def _get_thumbnail_path1200(self, original_image_path):
        # Assuming the thumbnails are saved in the 'thumbnails' subdirectory
        image_directory = 'images'
        thumbnail_directory = os.path.join(image_directory, 'thumbnail1200')
        
        # Construct the thumbnail filename based on the original image's filename
        thumbnail_filename = 'thumbnail1200_' + os.path.basename(original_image_path)

        # Construct the full path to the thumbnail
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)

        return thumbnail_path
    def _image_exists(self, image_id):
        query = 'SELECT id FROM images WHERE id = %s'
        values = (image_id,)
        result = self.db_manager.execute_query(query, values).fetchone()
        return result is not None

    def _save_image_and_thumbnail(self, image_file):
        # Specify the directory where you want to save the images
        image_directory = 'images'

        # Specify the subdirectory "thumbnails" inside the "images" directory
        thumbnail_directory = os.path.join(image_directory, 'thumbnails')
        thumbnail400_directory = os.path.join(image_directory, 'thumbnail400')
        thumbnail1200_directory = os.path.join(image_directory, 'thumbnail1200')

        # Create the directories if they don't exist
        os.makedirs(image_directory, exist_ok=True)
        os.makedirs(thumbnail_directory, exist_ok=True)
        os.makedirs(thumbnail400_directory, exist_ok=True)
        os.makedirs(thumbnail1200_directory, exist_ok=True)

        # Generate unique filenames for the image and thumbnail
        image_filename = f'image_{uuid.uuid4().hex}.png'
        thumbnail_filename = f'thumbnail_{uuid.uuid4().hex}.png'
        thumbnail400_filename = f'thumbnail400_{uuid.uuid4().hex}.png'
        thumbnail1200_filename = f'thumbnail1200_{uuid.uuid4().hex}.png'

        # Construct the full paths to save the image and thumbnail
        image_path = image_filename
        thumbnail_path = os.path.join(thumbnail_directory, thumbnail_filename)
        thumbnail400_path = os.path.join(thumbnail400_directory, thumbnail400_filename)
        thumbnail1200_path = os.path.join(thumbnail1200_directory, thumbnail1200_filename)

        # Save the image to the specified path
        with open(image_path, 'wb') as f:
            f.write(image_file.read())

        # Create the thumbnail and save it inside the "thumbnails" directory
        self._create_thumbnail(image_path, thumbnail_path)
        self._create_thumbnail400(image_path, thumbnail400_path)
        self._create_thumbnail1200(image_path, thumbnail1200_path)

        return image_path

    def _create_thumbnail(self, original_image_path, thumbnail_path):
        # Open the original image
        original_image = Image.open(original_image_path)

        # Create a thumbnail with a maximum size of 100x100 pixels
        thumbnail_size = (100, 100)
        thumbnail_image = original_image.copy()
        thumbnail_image.thumbnail(thumbnail_size)

        # Save the thumbnail to the specified path
        thumbnail_image.save(thumbnail_path)
        
    def _create_thumbnail400(self, original_image_path, thumbnail_path):
        # Open the original image
        original_image = Image.open(original_image_path)

        # Create a thumbnail with a maximum size of 100x100 pixels
        thumbnail_size = (400, 400)
        thumbnail_image = original_image.copy()
        thumbnail_image.thumbnail(thumbnail_size)

        # Save the thumbnail to the specified path
        thumbnail_image.save(thumbnail_path)
        
    def _create_thumbnail1200(self, original_image_path, thumbnail_path):
        # Open the original image
        original_image = Image.open(original_image_path)

        # Create a thumbnail with a maximum size of 100x100 pixels
        thumbnail_size = (1200, 1200)
        thumbnail_image = original_image.copy()
        thumbnail_image.thumbnail(thumbnail_size)

        # Save the thumbnail to the specified path
        thumbnail_image.save(thumbnail_path)
        
    def do_PUT(self):
        if self.path.startswith('/category'):
            try:
                # Extract category ID from the request path
                category_id = int(self.path.split('/')[2])

                # Parse the request body to get the updated category data
                content_length = int(self.headers['Content-Length'])
                updated_category_data = json.loads(self.rfile.read(content_length).decode('utf-8'))

                # Check if the 'name' field is provided in the updated data
                if 'name' not in updated_category_data:
                    self._send_response(400, 'Bad Request: Category name is required.')
                    return

                # Update the category in the database
                query = 'UPDATE categories SET name = %s WHERE id = %s'
                values = (updated_category_data['name'], category_id)
                affected_rows = self.db_manager.execute_query(query, values)

                if affected_rows > 0:
                    response_body = json.dumps({'id': category_id, 'name': updated_category_data['name']})
                    self._send_response(200, response_body)
                else:
                    self._send_response(404, 'Category not found')
            except Exception as e:
                print(f"Error updating category: {e}")
                self._send_response(500, 'Internal Server Error')
                
        elif self.path.startswith('/product'):
            try:
                content_length = int(self.headers['Content-Length'])
                product_data = json.loads(self.rfile.read(content_length).decode('utf-8'))

                # Validate required fields
                if 'name' not in product_data or 'category_ids' not in product_data or 'prices' not in product_data:
                    self._send_response(400, 'Bad Request: Product name, category_ids, and prices are required.')
                    return

                product_name = product_data['name']
                category_ids = product_data['category_ids']
                prices = product_data['prices']
                
                if not self._categories_exist(category_ids):
                    self._send_response(400, 'Invalid category_id provided')
                    return


                # Insert product into products table
                query_product = 'INSERT INTO products (name) VALUES (%s)'
                values_product = (product_name,)
                product_id = self.db_manager.execute_query(query_product, values_product)

                # Insert categories into product_category table within a transaction
                try:
                    query_category = 'INSERT INTO product_category (product_id, category_id) VALUES (%s, %s)'
                    values_category = [(product_id, category_id) for category_id in category_ids]
                    self.db_manager.execute_query_many(query_category, values_category)
                except Exception as e:
                    # Rollback the transaction on error
                    self.db_manager.execute_query('ROLLBACK')
                    self._send_response(500, f'Internal Server Error: {str(e)}')
                    return

                # Insert prices into the prices table within a transaction
                try:
                    query_price = 'INSERT INTO prices (product_id, price, quantity) VALUES (%s, %s, %s)'
                    values_price = [(product_id, price_data['price'], price_data['quantity']) for price_data in prices]
                    self.db_manager.execute_query_many(query_price, values_price)
                except Exception as e:
                    # Rollback the transaction on error
                    self.db_manager.execute_query('ROLLBACK')
                    self._send_response(500, f'Internal Server Error: {str(e)}')
                    return

                # Commit the transaction
                self.db_manager.execute_query('COMMIT')

                # Create the response body
                response_body = {
                    'id': product_id,
                    'name': product_name,
                    'category_ids': category_ids,
                    'prices': prices,
                }

                # Send the response
                self._send_response(201, json.dumps(response_body))
            except Exception as e:
                print(f"Error processing POST request: {e}")
                self._send_response(500, 'Internal Server Error')
            
        elif self.path.startswith('/image'):
            
            image_id = int(self.path.split('/')[2])

            content_type, _ = cgi.parse_header(self.headers['Content-Type'])

            # Check if the request is sending 'multipart/form-data'
            if content_type == 'multipart/form-data':
                form_data = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'PUT',
                            'CONTENT_TYPE': self.headers['Content-Type']}
                )

                # Extract image and product_id from the form data
                image_file = form_data['image'].file
                product_id = form_data.getvalue('product_id')

                # Save the updated image to a file
                image_path = self._save_image_and_thumbnail(image_file)

                # Update image information in the database
                query = 'UPDATE images SET product_id = %s, image_path = %s WHERE id = %s'
                values = (product_id, image_path, image_id)

                try:
                    affected_rows = self.db_manager.execute_query(query, values)
                    if affected_rows > 0:
                        self._send_response(200, 'Image updated successfully')
                    else:
                        self._send_response(404, 'Image not found')
                except Exception as e:
                    print(f"Error updating image: {e}")
                    self._send_response(500, 'Internal Server Error')
            else:
                self._send_response(400, 'Invalid Content-Type. Expected multipart/form-data')
        else:
            self._send_response(404, 'Not Found')
            
    def delete_category(self, category_id, soft_delete=False):
        try:
            if soft_delete:
                # Soft delete the category in the database
                query = 'UPDATE categories SET is_deleted = 1 WHERE id = %s'
            else:
                # Hard delete the category from the database
                query = 'DELETE FROM categories WHERE id = %s'

            values = (category_id,)
            affected_rows = self.db_manager.execute_query(query, values)

            if affected_rows > 0:
                self._send_response(200, 'delete completed')  # 204 No Content for successful delete
            else:
                self._send_response(404, 'Category not found')
        except Exception as e:
            print(f"Error deleting category: {e}")
            self._send_response(500, 'Internal Server Error')
            
    def do_DELETE(self):
        if self.path.startswith('/category'):
            category_id = int(self.path.split('/')[2])
            self.delete_category(category_id, soft_delete=False)
            
        elif self.path.startswith('/categories_soft/'):
            category_id = int(self.path.split('/')[2])
            self.delete_category(category_id, soft_delete=True)
            
        elif self.path.startswith('/product'):
            try:
                # Extract product ID from the request path
                product_id = int(self.path.split('/')[2])

                # Delete the product from the database
                query = 'DELETE FROM products WHERE id = %s'
                values = (product_id,)
                affected_rows = self.db_manager.execute_query(query, values)

                if affected_rows > 0:
                    self._send_response(204, 'delete completed')  # 204 No Content for successful deletion
                else:
                    self._send_response(404, 'Product not found')
            except Exception as e:
                print(f"Error deleting product: {e}")
                self._send_response(500, 'Internal Server Error')
        elif self.path.startswith('/image'):
            image_id = int(self.path.split('/')[2])

            # Delete image by ID
            query = 'DELETE FROM images WHERE id = %s'
            values = (image_id,)

            try:
                affected_rows = self.db_manager.execute_query(query, values)
                if affected_rows > 0:
                    self._send_response(204, '')  # 204 No Content for successful deletion
                else:
                    self._send_response(404, 'Image not found')
            except Exception as e:
                print(f"Error deleting image: {e}")
                self._send_response(500, 'Internal Server Error')
        else:
            self._send_response(404, 'Not Found')
        
            
            
        

if __name__ == '__main__':
    host = '127.0.0.1'
    port = 8080

    server = HTTPServer((host, port), CustomHandler)

    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    print(f'Starting server on http://{host}:{port}')

    try:
        server_thread.join()
    except KeyboardInterrupt:
        server.shutdown()
        print('Server stopped')