#ifndef CONFIG_H
#define CONFIG_H

/* Host computer name */
#cmakedefine HOSTNAME "@HOSTNAME@"

/* OS Name */
#cmakedefine SYSNAME "@SYSNAME@"

/* Project Name */
#cmakedefine PROJECT_NAME "@PROJECT_NAME_SHORT@"
#cmakedefine PROJECT_NAME_LONG "@PROJECT_NAME_LONG@"

/* DESCRIPTION */
#cmakedefine PROJECT_DESCRIPTION "@PROJECT_DESCRIPTION@"

/* Version */
#cmakedefine PROJECT_VERSION "@PROJECT_VERSION@"

/* Version Codename */
#cmakedefine CODENAME "@CODENAME@"

/* Copyright string */
#cmakedefine PROJECT_COPYRIGHT "@PROJECT_COPYRIGHT@"

/* Contact email */
#cmakedefine PROJECT_CONTACT "@PROJECT_CONTACT@"

/* Website */
#cmakedefine ORG_WEBSITE "@ORG_WEBSITE@"

/* Paths */
#define DATA_DIR "@YANER_DATA_DIR@"
#define PIXMAPS_DIR "@YANER_PIXMAPS_DIR@"
#define PROJECT_ICON PIXMAPS_DIR "yaner.png"

#endif //CONFIG_H
