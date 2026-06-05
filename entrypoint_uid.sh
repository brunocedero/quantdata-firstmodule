#!/bin/bash
# Si el UID con el que arrancamos no tiene una entrada en /etc/passwd, la creamos
# al vuelo apuntando al home de airflow. Así getpass.getuser() encuentra un nombre
# y Airflow arranca, sin importar qué UID le pasemos desde docker-compose.
if ! whoami &> /dev/null; then
  echo "airflow:x:$(id -u):0:airflow:/home/airflow:/bin/bash" >> /etc/passwd
fi

# Delegamos al entrypoint original de la imagen de Airflow, pasándole el comando
# (webserver / scheduler / bash -c ...) que venga de docker-compose.
exec /entrypoint "$@"