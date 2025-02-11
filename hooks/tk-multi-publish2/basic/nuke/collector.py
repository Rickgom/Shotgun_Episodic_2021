﻿# coding=utf-8
# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import nuke
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

# A look up of node types to parameters for finding outputs to publish
_NUKE_OUTPUTS = {
    "Read": "file",
    "Write": "file",
    "WriteGeo": "file",
}




class NukeSessionCollector(HookBaseClass):
    """
    Collector that operates on the current nuke/nukestudio session. Should
    inherit from the basic collector hook.
    """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this collector expects to receive
        through the settings parameter in the process_current_session and
        process_file methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """

        # grab any base class settings
        collector_settings = super(NukeSessionCollector, self).settings or {}

        # settings specific to this collector
        nuke_session_settings = {
            "Work Template": {
                "type": "template",
                "default": None,
                "description": "Template path for artist work files. Should "
                "correspond to a template defined in "
                "templates.yml. If configured, is made available"
                "to publish plugins via the collected item's "
                "properties. ",
            },
        }

        # update the base settings with these settings
        collector_settings.update(nuke_session_settings)

        return collector_settings

    def process_current_session(self, settings, parent_item):
        """
        Analyzes the current session open in Nuke/NukeStudio and parents a
        subtree of items under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """
        renderTypePath = nuke.selectedNode().knob('file').value()
        print renderTypePath
        publisher = self.parent
        engine = publisher.engine


        if (hasattr(engine, "studio_enabled") and engine.studio_enabled) or (
            hasattr(engine, "hiero_enabled") and engine.hiero_enabled
        ):

            # running nuke studio or hiero
            self.collect_current_nukestudio_session(settings, parent_item)

            # since we're in NS, any additional collected outputs will be
            # parented under the root item
            project_item = parent_item
        else:
            # running nuke. ensure additional collected outputs are parented
            # under the session


            if 'elements' in str(renderTypePath):
                print 'element mode selected'
                print renderTypePath
                project_item = self.collect_elements(settings, parent_item)
            else:
                print 'daily mode selected'
                print renderTypePath
                project_item = self.collect_daily_exr(settings, parent_item)

        # run node collection if not in hiero
        if hasattr(engine, "hiero_enabled") and not engine.hiero_enabled:
            if 'elements' in str(renderTypePath):
                pass
            else:
                self.collect_outputs(settings, project_item)
                self.collect_nuke_backup(settings, project_item)


    def collect_nuke_backup(self, settings, parent_item):
        """
        Analyzes the current session open in Nuke and parents a subtree of items
        under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """

        publisher = self.parent

        # get the current path
        pathEXR = nuke.selectedNode().knob('file').value()
        head, tail = os.path.split(pathEXR)       
        path = str(head)+'.nk'

        # determine the display name for the item
        if path:
            file_info = publisher.util.get_file_path_components(path)
            display_name = file_info["filename"]
        else:
            display_name = "Current Nuke Session"

        # create the session item for the publish hierarchy
        session_item = parent_item.create_item(
            "nuke.session", "Nuke Script", display_name
        )

        # get the icon path to display for this item
        icon_path = os.path.join(self.disk_location, os.pardir, "icons", "nuke.png")
        session_item.set_icon_from_path(icon_path)

        # if a work template is defined, add it to the item properties so
        # that it can be used by attached publish plugins
        work_template_setting = settings.get("Work Template")
        if work_template_setting:
            work_template = publisher.engine.get_template_by_name('nuke_shot_publish')

            # store the template on the item for use by publish plugins. we
            # can't evaluate the fields here because there's no guarantee the
            # current session path won't change once the item has been created.
            # the attached publish plugins will need to resolve the fields at
            # execution time.
            session_item.properties["work_template"] = work_template
            self.logger.debug("Work template defined for Nuke collection.")

        self.logger.info("Collected current Nuke script")
        session_item.context_change_allowed = True
        return session_item

    def collect_daily_exr(self, settings, parent_item):
        """
        Analyzes the current session open in Nuke and parents a subtree of items
        under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """

        publisher = self.parent

        # get the current path
        pathEXR = nuke.selectedNode().knob('file').value()
        head, tail = os.path.split(pathEXR)
        version_path = str(head)
        version_name = str(tail)[:-4]
        file_path = '%s/%s/%s.####.exr' % (version_path, version_name, version_name)





        # file exists, let the basic collector handle it
        item = super(NukeSessionCollector, self)._collect_file(
            parent_item, file_path, frame_sequence=False
        )





        current_engine = sgtk.platform.current_engine()
        render_template = current_engine.get_template_by_name('nuke_render_publish')
        render_path_fields = render_template.get_fields(file_path)
        shot_name = render_path_fields.get("Shot")
        task_name = render_path_fields.get("nuke.output")
        version_number = render_path_fields.get("version")


        item.properties["publish_version"] = version_number

        item.thumbnail_enabled = True
        item.context_change_allowed = True
        return item



    def collect_outputs(self, settings, parent_item):
        # iterate over all the known output types
        for node_type in _NUKE_OUTPUTS:

            # get all the instances of the node type
            all_nodes_of_type = [n for n in nuke.selectedNodes() if n.Class() == node_type]

            # iterate over each instance


            publisher = self.parent
            engine = publisher.engine

            first_frame = int(nuke.root()["first_frame"].value())
            last_frame = int(nuke.root()["last_frame"].value())
            for node in all_nodes_of_type:
                param_name = _NUKE_OUTPUTS[node_type]

                # evaluate the output path parameter which may include frame
                # expressions/format
                file_path = node[param_name].evaluate()



                self.logger.info("Processing %s node: %s" % (node_type, node.name()))

                # file exists, let the basic collector handle it
                item = super(NukeSessionCollector, self)._collect_file(
                    parent_item, file_path, frame_sequence=False
                )




                #SUBMIT FOR REVIEW


                # construct publish name:
                current_engine = sgtk.platform.current_engine()
                render_template = current_engine.get_template_by_name('nuke_shot_render_movie')
                render_path_fields = render_template.get_fields(file_path)

                shot_name = render_path_fields.get("Shot")
                task_name = render_path_fields.get("nuke.output")
                version_number = render_path_fields.get("version")

                item.properties["publish_version"] = version_number


                # the item has been created. update the display name to include
                # the nuke node to make it clear to the user how it was
                # collected within the current session.
                item.thumbnail_enabled = True
                item.context_change_allowed = True




    def collect_elements(self, settings, parent_item):
        # iterate over all the known output types
        for node_type in _NUKE_OUTPUTS:

            # get all the instances of the node type
            all_nodes_of_type = [n for n in nuke.selectedNodes() if n.Class() == node_type]

            # iterate over each instance


            publisher = self.parent
            engine = publisher.engine

            first_frame = int(nuke.root()["first_frame"].value())
            last_frame = int(nuke.root()["last_frame"].value())
            for node in all_nodes_of_type:
                param_name = _NUKE_OUTPUTS[node_type]

                # evaluate the output path parameter which may include frame
                # expressions/format
                file_path = node[param_name].evaluate()



                self.logger.info("Processing %s node: %s" % (node_type, node.name()))

                # file exists, let the basic collector handle it
                item = super(NukeSessionCollector, self)._collect_file(
                    parent_item, file_path, frame_sequence=True
                )




                #SUBMIT FOR REVIEW

                rendered_files = file_path


                # some files rendered, use first frame to get some publish item info
                path = rendered_files[0]


                publish_path = file_path
                print publish_path


                def get_movie_path():

                    head, tail = os.path.split(path)
                    movie_path = '%s.mov' % (head)
                    return movie_path

                # construct publish name:
                current_engine = sgtk.platform.current_engine()
                render_template = current_engine.get_template_by_name('nuke_element_publish')
                movie_template = current_engine.get_template_by_name('nuke_elements_movie')
                render_path_fields = render_template.get_fields(publish_path)

                rp_name = render_path_fields.get("name")
                rp_channel = render_path_fields.get("channel")
                if not rp_name and not rp_channel:
                    publish_name = "Publish"
                elif not rp_name:
                    publish_name = "Channel %s" % rp_channel
                elif not rp_channel:
                    publish_name = rp_name
                else:
                    publish_name = "%s, Channel %s" % (rp_name, rp_channel)
                shot_name = render_path_fields.get("Shot")
                task_name = render_path_fields.get("nuke.output")
                version_number = render_path_fields.get("version")

                sg_publish_data = ('%s_%s_%s.mov') % (shot_name, task_name, version_number)
                item.properties['sg_publish_data'] = sg_publish_data


                item.properties["color_space"] = 'Output - Rec709'

                item.properties["first_frame"] = first_frame
                item.properties["last_frame"] = last_frame
                item.properties["path"] = publish_path
                item.properties["publish_name"] = ('%s_%s') % (shot_name, task_name)
                item.properties["publish_template"] = render_template
                item.properties["work_template"] = render_template
                item.properties["sequence_paths"] = rendered_files
                item.properties["publish_version"] = version_number
                item.properties["movie_path"] = get_movie_path()
                                



               #elementEXR = nuke.selectedNode().knob('file').value()
               #head, tail = os.path.split(elementEXR)
               #basePath = list(os.path.split(head))[0]
               #elementVersion = list(os.path.split(head))[1]                
               #elementPath = '%s/_movies/%s.mov' % (basePath, elementVersion)



                item.thumbnail_enabled = True
                # the item has been created. update the display name to include
                # the nuke node to make it clear to the user how it was
                # collected within the current session.
                item.name = "%s (%s)" % (item.name, node.name())



    def _get_node_colorspace(self, node):
        """
        Get the colorspace for the specified nuke node

        :param node:    The nuke node to find the colorspace for
        :returns:       The string representing the colorspace for the node
        """
        cs_knob = node.knob("colorspace")
        if not cs_knob:
            return

        cs = cs_knob.value()
        # handle default value where cs would be something like: 'default (linear)'
        if cs.startswith("default (") and cs.endswith(")"):
            cs = cs[9:-1]
        return cs


def _session_path():
    """
    Return the path to the current session
    :return:
    """
    root_name = nuke.root().name()
    return None if root_name == "Root" else root_name
