from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd

# Setup Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")  # Ensure GUI is off
chrome_options.add_argument("--no-sandbox")

# Set path to chromedriver as per your configuration
webdriver_service = Service('/Users/matttoppi/Applications/chromedriver')

# Choose Chrome Browser
driver = webdriver.Chrome(service=webdriver_service, options=chrome_options)

# Go to the page that we will be scraping
driver.get('https://nextgenstats.nfl.com/stats/receiving#yards')

# Wait for the dynamically loaded elements to show up
WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CLASS_NAME, "el-table__body-wrapper"))
)

# Extract headers
headers = [header.text for header in driver.find_elements(By.XPATH, "//div[contains(@class,'el-table__header-wrapper')]//th")]

# Extract the rows
rows = []
table_body = driver.find_element(By.CLASS_NAME, 'el-table__body-wrapper')
table_rows = table_body.find_elements(By.XPATH, ".//div[contains(@class, 'el-table__row')]")

for row in table_rows:
    # Find all the cells in the row
    cells = row.find_elements(By.XPATH, ".//div[contains(@class, 'cell')]")
    row_data = [cell.text for cell in cells]
    rows.append(row_data)

# Close the browser
driver.quit()

# Create the DataFrame and save to CSV if data is found
if headers and rows:
    df = pd.DataFrame(rows, columns=headers)
    df.to_csv('/datarepo/nextgenstats.csv', index=False)
    print(df.head())
    print('CSV file has been created.')
else:
    print("No data found.")
